"""Vercel serverless entry — exposes the FastAPI app at /api/*."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in (ROOT / "backend", ROOT / "server", ROOT):
    text = str(part)
    if text not in sys.path:
        sys.path.insert(0, text)

from server.main import app  # noqa: E402
