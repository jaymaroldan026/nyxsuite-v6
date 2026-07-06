"""Global stop/start hotkeys for the Nyx Suite.

Two system-wide hotkeys, one per product, each toggling its runner through the
same Start/Stop actions the dashboard uses:

- **Ctrl+F8** — Nyx (Bitmoji runner)
- **Ctrl+F7** — Nyxify (profile-creation runner)

They fire even while the AdsPower window has focus because they are a global
keyboard hook (``pynput``). Each key always controls its own product, so
stopping Nyxify never depends on which dashboard tab was last viewed and can
never accidentally start Nyx instead.

Why a raw ``keyboard.Listener`` and not ``pynput.keyboard.GlobalHotKeys``:
``GlobalHotKeys`` was verified to **never fire** on this setup (the raw hook sees
the keys, but the hotkey matcher does not), which is why the first version was
silent. We detect Ctrl+F7/F8 ourselves on a raw listener (proven to fire) with a
short debounce against key auto-repeat.

The bridge owns the listener so a hotkey can start a stopped runner too. A
distinct built-in tone plays per action (low descending double-beep = stopped,
higher rising double-beep = started) so you hear that the key was caught — no
asset files.

On macOS, global hotkeys require the host app to have **Accessibility**
permission (*System Settings → Privacy & Security → Accessibility*).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from core.logger import logger

_DEBOUNCE_SECONDS = 0.4         # ignore key auto-repeat / double-fire

_listener = None
_listener_lock = threading.Lock()


def start_product_hotkeys(bindings):
    """Start ONE global listener that dispatches per-key actions (idempotent).

    ``bindings`` maps a key name (``"f7"``/``"f8"``) to ``(scope, action)``:
    ``scope`` names the product for log messages, ``action`` is a callback that
    receives ``scope`` and returns a dict with ``action`` set to ``"start"`` or
    ``"stop"``. Every binding requires Ctrl held.

    Best-effort: if ``pynput`` is missing or the OS blocks the hook it logs a
    warning and returns ``None`` — the dashboard/tray controls are unaffected."""
    global _listener
    normalized = {}
    for key_name, (scope, action) in (bindings or {}).items():
        normalized[str(key_name).strip().lower()] = (str(scope or "runner"), action)
    if not normalized:
        return None

    with _listener_lock:
        if _listener is not None:
            return _listener
        try:
            from pynput import keyboard
        except Exception as exc:
            logger.warning(
                f"Global stop/start hotkeys unavailable (pynput not installed?): {exc}")
            return None
        try:
            ctrl_keys = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
            key_map = {}
            for key_name, entry in normalized.items():
                key_obj = getattr(keyboard.Key, key_name, None)
                if key_obj is None:
                    logger.warning(f"Unknown hotkey key name {key_name!r}; skipped.")
                    continue
                key_map[key_obj] = (key_name, entry)
            if not key_map:
                return None

            state = {"ctrl": False, "last": {}}

            def on_press(key):
                if key in ctrl_keys:
                    state["ctrl"] = True
                    return
                entry = key_map.get(key)
                if entry is None or not state["ctrl"]:
                    return
                key_name, (scope, action) = entry
                now = time.monotonic()
                if now - state["last"].get(key_name, 0.0) < _DEBOUNCE_SECONDS:
                    return
                state["last"][key_name] = now
                handle_start_stop_hotkey(scope, action, label=f"Ctrl+{key_name.upper()}")

            def on_release(key):
                if key in ctrl_keys:
                    state["ctrl"] = False

            lst = keyboard.Listener(on_press=on_press, on_release=on_release)
            lst.daemon = True
            lst.start()
            _listener = lst
            labels = ", ".join(
                f"Ctrl+{name.upper()}={scope}" for name, (scope, _a) in sorted(normalized.items())
            )
            logger.info(f"Global stop/start hotkeys active: {labels}.")
            return lst
        except Exception as exc:
            logger.warning(f"Could not start the global stop/start hotkeys: {exc}")
            return None


def start_stop_hotkey(scope: str = "all", action=None):
    """Legacy single-hotkey entry point: Ctrl+F8 only (kept for compatibility)."""
    return start_product_hotkeys({"f8": (scope, action)})


def stop_hotkey():
    global _listener
    with _listener_lock:
        if _listener is not None:
            try:
                _listener.stop()
            except Exception:
                pass
            _listener = None


def handle_start_stop_hotkey(scope: str, action=None, label: str = "Ctrl+F8"):
    """Run the configured hotkey action and play the matching tone."""
    try:
        if action is None:
            return _stop_current_process(scope, label=label)

        result = action(scope)
        if not isinstance(result, dict):
            result = {"ok": True, "action": "stop"}

        action_name = str(result.get("action") or "stop").strip().lower()
        product = str(result.get("product") or scope or "runner").strip()
        message = str(result.get("message") or "").strip()
        if message:
            logger.info(f"{label}: {message}")
        else:
            logger.info(f"{label}: {action_name} {product}.")

        _play_async(_play_start_tone if action_name == "start" else _play_stop_tone)
        return result
    except Exception as exc:
        logger.warning(f"Stop/start hotkey failed: {exc}")
        return {"ok": False, "error": str(exc)}


def _stop_current_process(scope: str, label: str = "Ctrl+F8"):
    """Legacy fallback for direct runner launches without a bridge callback."""
    try:
        logger.info(f"{label}: stopping {scope}.")
        _play_async(_play_stop_tone)
        # Small delay so the tone plays before the process exits
        time.sleep(0.3)
        sys.exit(0)
    except Exception as exc:
        logger.warning(f"Stop hotkey failed: {exc}")


# ---------------------------------------------------------------------------
# Tones — distinct, built-in, no asset files (mirrors nyxify_runner's beep)
# ---------------------------------------------------------------------------
def _play_async(fn):
    """Play a tone off the listener thread so the hotkey stays responsive."""
    threading.Thread(target=fn, daemon=True).start()


def _play_stop_tone():
    # Low, descending double-beep = "stopped".
    _play_tones([(440, 120), (330, 170)], mac_sound="Funk")


def _play_start_tone():
    # Higher, rising double-beep = "go".
    _play_tones([(660, 110), (880, 150)], mac_sound="Glass")


def _play_tones(win_beeps, mac_sound):
    try:
        if sys.platform.startswith("win"):
            import winsound
            for freq, ms in win_beeps:
                winsound.Beep(int(freq), int(ms))
            return
        if sys.platform == "darwin":
            for command in (
                ["afplay", f"/System/Library/Sounds/{mac_sound}.aiff"],
                ["osascript", "-e", "beep 1"],
            ):
                try:
                    subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    continue
        print("\a", end="", flush=True)
    except Exception as exc:
        logger.warning(f"Could not play hotkey tone: {exc}")
