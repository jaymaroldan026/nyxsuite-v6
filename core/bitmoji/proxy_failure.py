import re
import socket


# Profile proxy is bad but the host itself is online: give the proxy ~100s to
# come back (Chrome's "No internet / ERR_PROXY_CONNECTION_FAILED" page). We
# refresh periodically within this window; if it still fails the profile is
# declared a proxy_error and the runner moves to the next account. Kept short so
# a dead proxy doesn't stall the queue.
BITMOJI_PROXY_FAILURE_ONLINE_TIMEOUT_SECONDS = 100
# Host's own internet looks down (not just the profile proxy): wait longer so a
# transient Wi-Fi/router blip doesn't mass-fail the whole batch as proxy_error.
BITMOJI_PROXY_FAILURE_OFFLINE_TIMEOUT_SECONDS = 300
HOST_CONNECTIVITY_PROBE_TARGETS = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 53),
)

_PROXY_ERROR_CODE_RE = re.compile(
    r"\bERR_(?:PROXY|TUNNEL|SOCKS|NO_SUPPORTED_PROXIES)[A-Z0-9_]*\b",
    re.IGNORECASE,
)

_NAVIGATION_PROXY_TOKENS = [
    "net::err_proxy",
    "net::err_tunnel",
    "net::err_socks",
    "err_proxy_connection_failed",
    "err_tunnel_connection_failed",
    "err_socks_connection_failed",
    "err_no_supported_proxies",
    "proxy connection failed",
    "proxy authentication",
    "proxy server",
]


class BitmojiProxyFailureError(Exception):
    """Raised when the Bitmoji flow is blocked by a profile proxy failure."""


def _compact(value, limit=180):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def is_proxy_navigation_error(message):
    normalized = str(message or "").lower()
    if not normalized:
        return False
    if _PROXY_ERROR_CODE_RE.search(normalized):
        return True
    return any(token in normalized for token in _NAVIGATION_PROXY_TOKENS)


def probe_host_connectivity(timeout_seconds=2.0, targets=None):
    for host, port in (targets or HOST_CONNECTIVITY_PROBE_TARGETS):
        try:
            with socket.create_connection((host, int(port)), timeout=float(timeout_seconds)):
                return True
        except OSError:
            continue
    return False


def select_proxy_failure_recovery(probe_func=probe_host_connectivity):
    try:
        host_online = bool(probe_func())
    except Exception:
        host_online = False

    if host_online:
        return {
            "failure_kind": "profile_proxy_failure",
            "host_online": True,
            "timeout_seconds": BITMOJI_PROXY_FAILURE_ONLINE_TIMEOUT_SECONDS,
        }

    return {
        "failure_kind": "host_offline_or_no_internet",
        "host_online": False,
        "timeout_seconds": BITMOJI_PROXY_FAILURE_OFFLINE_TIMEOUT_SECONDS,
    }


def detect_proxy_failure_signal(url="", text="", error=""):
    if is_proxy_navigation_error(error):
        match = _PROXY_ERROR_CODE_RE.search(str(error or ""))
        if match:
            return f"navigation error {match.group(0).upper()}"
        return f"navigation proxy error: {_compact(error)}"

    normalized_url = str(url or "").strip().lower()
    normalized_text = str(text or "").strip().lower()
    combined = f"{normalized_url}\n{normalized_text}"

    if "start.adspower.net" in normalized_url and "proxy failure" in normalized_text:
        return "AdsPower proxy failure page"

    if "proxy failure" in normalized_text and "adspower" in combined:
        return "AdsPower proxy failure page"

    match = _PROXY_ERROR_CODE_RE.search(combined)
    if match:
        return f"browser error {match.group(0).upper()}"

    if "no internet" in normalized_text and "proxy server" in normalized_text:
        return "Chrome no-internet proxy page"

    if "there is something wrong with the proxy server" in normalized_text:
        return "Chrome proxy server error page"

    return ""
