import json

from core.process_utils import APP_DATA_DIR

DATA_DIR = APP_DATA_DIR / "data"
CONFIG_PATH = DATA_DIR / "nyxify_config.json"
DEFAULTS = {
    "max_parallel_profiles": 1,
    "temporary_profile_name": "Snapchat:",
    "adspower_group": "Snapchat",
    "extension_category": "Snap",
    "tag_one": "Snapchat",
    "tag_two": "",
    "adspower_tags_enabled": True,
    "blocked_proxies": [],
    "proxy_blocker_enabled": True,
    "proxy_checker_enabled": True,
    "push_adspower_id_enabled": True,
    "full_auto_mode_enabled": False,
    "launch_on_windows_startup": False,
    "names_dir": "",
}


def _safe_int(value, default):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _safe_str(value, default=""):
    value = str(value or "").strip()
    if value:
        return value
    return default


def _stored_str(raw, key, default=""):
    if key not in raw:
        return default
    return str(raw.get(key) or "").strip()


def _updated_str(updates, current, key, *, allow_blank=True, blank_default=None):
    if key not in updates:
        return current[key]
    value = str(updates.get(key) or "").strip()
    if value or allow_blank:
        return value
    return blank_default if blank_default is not None else current[key]


def _safe_bool(value, default):
    if value is None:
        return default
    return bool(value)


def _safe_proxy_patterns(value):
    if isinstance(value, str):
        items = [part.strip() for part in value.splitlines()]
    elif isinstance(value, list):
        items = [str(part).strip() for part in value]
    else:
        items = []
    return [item for item in items if item]


def load_nyxify_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8") or "{}")
    except Exception:
        raw = {}

    return {
        "max_parallel_profiles": _safe_int(raw.get("max_parallel_profiles"), DEFAULTS["max_parallel_profiles"]),
        "temporary_profile_name": _stored_str(raw, "temporary_profile_name", DEFAULTS["temporary_profile_name"]),
        "adspower_group": _stored_str(raw, "adspower_group", DEFAULTS["adspower_group"]),
        "extension_category": _stored_str(raw, "extension_category", DEFAULTS["extension_category"]),
        "tag_one": _stored_str(raw, "tag_one", DEFAULTS["tag_one"]),
        "tag_two": _stored_str(raw, "tag_two", DEFAULTS["tag_two"]),
        "adspower_tags_enabled": _safe_bool(
            raw.get("adspower_tags_enabled"),
            DEFAULTS["adspower_tags_enabled"],
        ),
        "blocked_proxies": _safe_proxy_patterns(raw.get("blocked_proxies") or raw.get("banned_proxies")),
        "proxy_blocker_enabled": _safe_bool(raw.get("proxy_blocker_enabled"), DEFAULTS["proxy_blocker_enabled"]),
        "proxy_checker_enabled": _safe_bool(raw.get("proxy_checker_enabled"), DEFAULTS["proxy_checker_enabled"]),
        "push_adspower_id_enabled": _safe_bool(
            raw.get("push_adspower_id_enabled"),
            DEFAULTS["push_adspower_id_enabled"],
        ),
        "full_auto_mode_enabled": _safe_bool(
            raw.get("full_auto_mode_enabled"),
            DEFAULTS["full_auto_mode_enabled"],
        ),
        "launch_on_windows_startup": _safe_bool(
            raw.get("launch_on_windows_startup"),
            DEFAULTS["launch_on_windows_startup"],
        ),
        "names_dir": _safe_str(raw.get("names_dir"), DEFAULTS["names_dir"]),
    }


def save_nyxify_config(updates):
    current = load_nyxify_config()
    next_config = {
        "max_parallel_profiles": _safe_int(
            updates.get("max_parallel_profiles", current["max_parallel_profiles"]),
            current["max_parallel_profiles"],
        ),
        "temporary_profile_name": _updated_str(
            updates,
            current,
            "temporary_profile_name",
            allow_blank=False,
            blank_default=DEFAULTS["temporary_profile_name"],
        ),
        "adspower_group": _updated_str(updates, current, "adspower_group"),
        "extension_category": _updated_str(
            updates,
            current,
            "extension_category",
            allow_blank=False,
            blank_default=DEFAULTS["extension_category"],
        ),
        "tag_one": _updated_str(updates, current, "tag_one"),
        "tag_two": _updated_str(updates, current, "tag_two"),
        "adspower_tags_enabled": _safe_bool(
            updates.get("adspower_tags_enabled"),
            current["adspower_tags_enabled"],
        ),
        "blocked_proxies": _safe_proxy_patterns(
            updates.get("blocked_proxies", updates.get("banned_proxies", current["blocked_proxies"]))
        ),
        "proxy_blocker_enabled": _safe_bool(
            updates.get("proxy_blocker_enabled"),
            current["proxy_blocker_enabled"],
        ),
        "proxy_checker_enabled": _safe_bool(
            updates.get("proxy_checker_enabled"),
            current["proxy_checker_enabled"],
        ),
        "push_adspower_id_enabled": _safe_bool(
            updates.get("push_adspower_id_enabled"),
            current["push_adspower_id_enabled"],
        ),
        "full_auto_mode_enabled": _safe_bool(
            updates.get("full_auto_mode_enabled"),
            current["full_auto_mode_enabled"],
        ),
        "launch_on_windows_startup": _safe_bool(
            updates.get("launch_on_windows_startup"),
            current["launch_on_windows_startup"],
        ),
        "names_dir": _updated_str(updates, current, "names_dir"),
    }
    CONFIG_PATH.write_text(json.dumps(next_config, indent=2), encoding="utf-8")
    return next_config
