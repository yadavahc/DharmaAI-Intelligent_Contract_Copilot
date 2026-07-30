"""Test configuration.

Demo mode is forced before `app.config` is imported so no test can reach the
network or spend money, regardless of what is in the developer's `.env`.
"""

from __future__ import annotations

import os

os.environ["DHARMA_DEMO_MODE"] = "true"
os.environ.pop("OPENAI_API_KEY", None)
