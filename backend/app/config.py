"""Central settings. Every secret arrives via environment / `.env` — never inline."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Anchor paths on the backend package, not on a guessed repo root.
#
#   local container : /app/app/config.py          -> BACKEND_DIR = /app
#   local checkout  : <root>/backend/app/config.py -> BACKEND_DIR = <root>/backend
#
# Both are correct. `parents[2]` alone is not: inside the image it resolves to "/",
# which made the app try to create /backend/storage and crash on PermissionError.
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # In the container these files are absent (see .dockerignore) and config
        # arrives purely from the environment, which is the intended behaviour.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── OpenAI ──
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = 60.0

    # ── Demo mode ──
    # Deterministic canned agent output; no network, no spend. Auto-enables when
    # no API key is present so the demo never hard-fails in front of a judge.
    dharma_demo_mode: bool = False

    # ── Postgres ──
    database_url: str = "postgresql://dharma:dharma@localhost:5432/dharma"

    # ── Qdrant ──
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    # 1536 = text-embedding-3-small. Must match the embedding model.
    embedding_dim: int = 1536

    # ── Server ──
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    # Held as a raw string, not List[str]: pydantic-settings attempts to JSON-decode
    # complex field types read from a dotenv file *before* validators run, so a
    # plain `BACKEND_CORS_ORIGINS=http://localhost:3000` raises a SettingsError.
    # Parsing in the `backend_cors_origins` property keeps the comma-separated form
    # working and is not sensitive to pydantic-settings' decoding behaviour.
    backend_cors_origins_raw: str = Field(
        default="http://localhost:3000",
        validation_alias="BACKEND_CORS_ORIGINS",
    )

    # ── Writable scratch dir (SQLite fallback, resources) ──
    # The Docker image creates and chowns /app/storage for this.
    storage_dir: Path = Field(
        default=BACKEND_DIR / "storage", validation_alias="STORAGE_DIR"
    )

    # ── Risk + negotiation tuning ──
    risk_high_threshold: int = 70
    risk_medium_threshold: int = 40
    negotiation_max_rounds: int = 4

    @property
    def backend_cors_origins(self) -> List[str]:
        """Comma-separated origins, parsed. Falls back to localhost:3000 if empty."""
        origins = [o.strip() for o in self.backend_cors_origins_raw.split(",") if o.strip()]
        return origins or ["http://localhost:3000"]

    @property
    def demo_mode(self) -> bool:
        """Explicitly requested, or forced because there is no usable API key."""
        if self.dharma_demo_mode:
            return True
        key = (self.openai_api_key or "").strip()
        return not key or key.startswith("sk-replace")

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise a Prisma-style URL into a SQLAlchemy psycopg-3 URL."""
        url = self.database_url.split("?", 1)[0]
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


# ─────────────────────────────────────────────────────────────────────────────
# Secret loading
# ─────────────────────────────────────────────────────────────────────────────

# Secrets that should never be read from a plain env var in production.
_SECRET_FIELDS = ("OPENAI_API_KEY", "QDRANT_API_KEY", "DATABASE_URL")

# Where orchestrators mount secret files by convention.
_SECRET_MOUNTS = (Path("/run/secrets"), Path("/var/run/secrets"))


def _load_file_secrets() -> List[str]:
    """Support the `*_FILE` convention used by Docker and Kubernetes secrets.

    `.env` is fine for local development, but in production a secret in an
    environment variable is visible to `docker inspect`, to every child process,
    and to any crash reporter that dumps the environment. Both Docker Swarm and
    Kubernetes instead mount secrets as files and expect the app to read them.

    Precedence, lowest to highest:
        .env file  →  environment variable  →  OPENAI_API_KEY_FILE  →  /run/secrets/<name>

    Returns the names of secrets that were loaded from a file, so startup can
    report which mechanism supplied each one.
    """
    loaded: List[str] = []

    for name in _SECRET_FIELDS:
        # 1. Explicit <NAME>_FILE pointer.
        pointer = os.environ.get(f"{name}_FILE")
        candidates = [Path(pointer)] if pointer else []

        # 2. Conventional mount paths, checked lowercase and uppercase.
        for mount in _SECRET_MOUNTS:
            candidates.extend([mount / name.lower(), mount / name])

        for path in candidates:
            try:
                if path.is_file():
                    value = path.read_text(encoding="utf-8").strip()
                    if value:
                        os.environ[name] = value
                        loaded.append(f"{name}←{path}")
                        break
            except OSError as exc:
                logger.warning("Could not read secret file %s: %s", path, exc)

    return loaded


def _audit_secrets(settings: "Settings", file_loaded: List[str]) -> None:
    """Warn about placeholder or missing secrets at startup, not at first use."""
    if file_loaded:
        logger.info("Secrets loaded from mounted files: %s", ", ".join(file_loaded))

    key = (settings.openai_api_key or "").strip()
    if not key:
        logger.warning(
            "No OPENAI_API_KEY set — running in demo mode with deterministic agent "
            "output. Set a real key (or mount OPENAI_API_KEY_FILE) for live agents."
        )
    elif key.startswith("sk-replace"):
        logger.warning(
            "OPENAI_API_KEY is still the placeholder from .env.example — demo mode "
            "will be used. Replace it with a real key for live agents."
        )

    if "dharma:dharma@" in settings.database_url:
        logger.warning(
            "Using the default Postgres credentials from .env.example. Fine for a "
            "local demo; change them before exposing this beyond localhost."
        )


@lru_cache
def get_settings() -> Settings:
    file_loaded = _load_file_secrets()
    settings = Settings()

    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # A scratch directory must never prevent the service from booting. It is
        # only needed for the SQLite fallback; Postgres deployments never touch it.
        logger.warning(
            "Could not create storage dir %s (%s). Set STORAGE_DIR to a writable "
            "path if the SQLite fallback is needed.",
            settings.storage_dir,
            exc,
        )

    _audit_secrets(settings, file_loaded)
    return settings


settings = get_settings()
