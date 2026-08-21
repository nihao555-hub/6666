"""Multi-tenant listing service.

The protocol layer under `backend/` is also run as standalone scripts
(`python3 backend/ping.py`), so those modules import each other flatly. Put the
directory on the path once here instead of duplicating the shim per module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
