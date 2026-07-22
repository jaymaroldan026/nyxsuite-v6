import json

from core.process_utils import APP_DATA_DIR

DATA_DIR = APP_DATA_DIR / "data"
CONFIG_PATH = DATA_DIR / "bridge_config.json"
DEFAULTS = {
    "transparent_tray_icon": False,
}


def _safe_bool(value, default):
    if value is None:
        return default
    return bool(value)


def load_bridge_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8") or "{}")
    except Exception:
        raw = {}

    return {
        "transparent_tray_icon": _safe_bool(
            raw.get("transparent_tray_icon"),
            DEFAULTS["transparent_tray_icon"],
        ),
    }


def save_bridge_config(updates):
    current = load_bridge_config()
    next_config = {
        "transparent_tray_icon": _safe_bool(
            updates.get("transparent_tray_icon"),
            current["transparent_tray_icon"],
        ),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(next_config, indent=2), encoding="utf-8")
    return next_config
