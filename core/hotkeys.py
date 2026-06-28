"""Global pause/resume hotkey for the Nyx Suite.

A single system-wide **Ctrl+F8** pauses/resumes the runner. It fires even while
the AdsPower window has focus because it is a global keyboard hook (``pynput``).

Why a raw ``keyboard.Listener`` and not ``pynput.keyboard.GlobalHotKeys``:
``GlobalHotKeys`` was verified to **never fire** on this setup (the raw hook sees
the keys, but the hotkey matcher does not), which is why the first version was
silent. We detect Ctrl+F8 ourselves on a raw listener (proven to fire) with a
short debounce against key auto-repeat.

The listener is hosted **inside each runner process** (Nyx = ``main.py``,
Nyxify = ``nyxify_runner.py``) with a ``scope`` so each toggles only *its own*
pause flag (``core.runner_flags``):

* it runs in the very process doing the work, so it pauses the *current* run
  (the Bitmoji flow polls the pause flag mid-run via ``wait_if_paused``);
* it needs no bridge — only a *running* runner has a listener, so Ctrl+F8
  naturally affects "whatever is running";
* two runners toggling two different flags can't cancel each other out (the bug
  a single shared toggle would have).

A distinct built-in tone plays per action (low descending double-beep = pause,
higher rising = resume) so you hear that the key was caught — no asset files.

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


def start_pause_hotkey(scope: str = "all"):
    """Start the global Ctrl+F8 listener on a daemon thread (idempotent).

    ``scope`` selects which pause flag(s) the key toggles:
      * ``"nyx"``     — only the Nyx runner (used by ``main.py``)
      * ``"nyxify"``  — only the Nyxify runner (used by ``nyxify_runner.py``)
      * ``"all"``     — both (combined toggle; for a single host like the bridge)

    Best-effort: if ``pynput`` is missing or the OS blocks the hook it logs a
    warning and returns ``None`` — the dashboard/tray pause buttons are
    unaffected."""
    global _listener
    with _listener_lock:
        if _listener is not None:
            return _listener
        try:
            from pynput import keyboard
        except Exception as exc:
            logger.warning(
                f"Global pause hotkey unavailable (pynput not installed?): {exc}")
            return None
        try:
            ctrl_keys = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
            state = {"ctrl": False, "last": 0.0}

            def on_press(key):
                if key in ctrl_keys:
                    state["ctrl"] = True
                    return
                if key == keyboard.Key.f8 and state["ctrl"]:
                    now = time.monotonic()
                    if now - state["last"] < _DEBOUNCE_SECONDS:
                        return
                    state["last"] = now
                    _on_toggle(scope)

            def on_release(key):
                if key in ctrl_keys:
                    state["ctrl"] = False

            lst = keyboard.Listener(on_press=on_press, on_release=on_release)
            lst.daemon = True
            lst.start()
            _listener = lst
            logger.info(f"Global pause/resume hotkey active: Ctrl+F8 (scope={scope}).")
            return lst
        except Exception as exc:
            logger.warning(f"Could not start the global pause hotkey: {exc}")
            return None


def stop_pause_hotkey():
    global _listener
    with _listener_lock:
        if _listener is not None:
            try:
                _listener.stop()
            except Exception:
                pass
            _listener = None


def _on_toggle(scope: str):
    """Flip the pause flag(s) for ``scope`` and play the matching tone. Pausing a
    *running* runner takes effect on its next poll; the Nyx Bitmoji flow also
    checks the flag mid-run, so the current automation pauses too."""
    try:
        from core import runner_flags

        if scope == "nyx":
            new_paused = not runner_flags.nyx_is_paused()
            runner_flags.nyx_set_paused(new_paused)
            logger.info(f"Ctrl+F8: {'paused' if new_paused else 'resumed'} Nyx.")
        elif scope == "nyxify":
            new_paused = not runner_flags.nyxify_is_paused()
            runner_flags.nyxify_set_paused(new_paused)
            logger.info(f"Ctrl+F8: {'paused' if new_paused else 'resumed'} Nyxify.")
        else:  # "all" — combined toggle (pause if anything is running)
            new_paused = (not runner_flags.nyx_is_paused()) or \
                         (not runner_flags.nyxify_is_paused())
            runner_flags.nyx_set_paused(new_paused)
            runner_flags.nyxify_set_paused(new_paused)
            logger.info(f"Ctrl+F8: {'paused' if new_paused else 'resumed'} Nyx + Nyxify.")

        _play_async(_play_pause_tone if new_paused else _play_resume_tone)
    except Exception as exc:
        logger.warning(f"Pause hotkey toggle failed: {exc}")


# ---------------------------------------------------------------------------
# Tones — distinct, built-in, no asset files (mirrors nyxify_runner's beep)
# ---------------------------------------------------------------------------
def _play_async(fn):
    """Play a tone off the listener thread so the hotkey stays responsive."""
    threading.Thread(target=fn, daemon=True).start()


def _play_pause_tone():
    # Low, descending double-beep = "stopped".
    _play_tones([(440, 120), (330, 170)], mac_sound="Funk")


def _play_resume_tone():
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
