# Python 3.11 satisfies lyzr-automata's declared `Requires-Python: >=3.8.1,<3.12`
# natively, so the genuine SDK installs here with no version override.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is used by the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-lyzr.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    # --no-deps keeps lyzr-automata's openai==1.3.4 pin from downgrading the
    # modern SDK. Dharma AI implements Lyzr's own AIModel ABC instead of using
    # its bundled OpenAIModel, so that pin is never needed.
    # See requirements-lyzr.txt for the full rationale.
    && pip install --no-deps -r requirements-lyzr.txt \
    # Fail the build loudly if the genuine SDK did not land, rather than silently
    # shipping an image that falls back to the shim.
    && python -c "import lyzr_automata, importlib.metadata as m; \
print('lyzr-automata', m.version('lyzr-automata'), 'OK')"

COPY . .

RUN mkdir -p /app/storage && useradd -m -u 1000 dharma && chown -R dharma:dharma /app
USER dharma

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
