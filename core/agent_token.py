"""Per-install agent token for the local API + dashboard.

A random token generated once and stored under the app-data dir. It is required
on state-changing endpoints so that arbitrary websites — which *can* issue
cross-origin POSTs to 127.0.0.1 — cannot control the agent or trigger updates.
CORS alone does not stop side-effecting POSTs, so the token is
the real guard.

Distribution:
- the dashboard gets it injected into index.html (window.__NYX_TOKEN__);
- the extensions get it via the native-messaging Connect handshake (or copy-paste
  from web Settings).
"""

import secrets
from pathlib import Path

from core.process_utils import APP_DATA_DIR

TOKEN_FILE = APP_DATA_DIR / "agent_token.txt"


def get_or_create_token() -> str:
    """Return the stored token, generating and persisting one on first use."""
    try:
        if TOKEN_FILE.exists():
            existing = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except Exception:
        pass
    token = secrets.token_hex(24)
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token, encoding="utf-8")
    except Exception:
        pass
    return token


def read_token() -> str:
    """Return the stored token, or '' if none exists yet (does not create one)."""
    try:
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""
