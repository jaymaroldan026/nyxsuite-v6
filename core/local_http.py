"""Shared CORS + token helpers for the local API and dashboard servers.

The token is the primary guard on state-changing requests. CORS is tightened so
that arbitrary websites cannot *read* responses (e.g. the dashboard HTML, which
carries the injected token) — only the dashboard origin and the browser
extensions are echoed an Access-Control-Allow-Origin.
"""


def is_allowed_origin(origin: str) -> bool:
    o = (origin or "").strip()
    if not o:
        return True  # no Origin header = same-origin or a non-browser client
    if o.startswith("chrome-extension://") or o.startswith("moz-extension://"):
        return True
    for host in ("http://127.0.0.1", "http://localhost"):
        if o == host or o.startswith(host + ":"):
            return True
    return False


def apply_cors(handler) -> None:
    """Send CORS headers on a BaseHTTPRequestHandler response, origin-allowlisted.

    For a disallowed cross-origin request we omit Access-Control-Allow-Origin
    entirely, so the browser blocks the caller from reading the response.
    """
    origin = handler.headers.get("Origin", "")
    if not origin:
        handler.send_header("Access-Control-Allow-Origin", "*")
    elif is_allowed_origin(origin):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    # else: no ACAO header -> cross-origin read blocked by the browser
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-Nyx-Token, X-Nyxify-Token")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


def extract_token(handler, payload=None, query_token: str = "") -> str:
    """Pull a supplied token from (in order) query string, JSON body, headers."""
    supplied = (query_token or "").strip()
    if not supplied and isinstance(payload, dict):
        supplied = str(payload.get("token", "") or "").strip()
    if not supplied:
        supplied = (handler.headers.get("X-Nyx-Token", "")
                    or handler.headers.get("X-Nyxify-Token", "")).strip()
    return supplied
