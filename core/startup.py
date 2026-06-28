"""Cross-platform run-on-login for the Nyx Suite bridge agent.

Unified interface wrapping OS-specific mechanisms:
  - Windows: HKCU\\...\\Run registry
  - macOS: ~/Library/LaunchAgents/com.nyxsuite.agent.plist + launchctl
  - Linux: ~/.config/autostart/nyxsuite-agent.desktop (XDG autostart)

Uses the portable launcher scripts (portable_launch_nyx.sh / .ps1) to
bootstrap the agent regardless of frozen/source mode.
"""

import os
import sys
from pathlib import Path

from core.process_utils import ROOT_DIR, resolve_python_executable

LAUNCHER_NAME = "NyxSuiteBridge"


def _quote(s):
    return '"' + str(s) + '"'


def _resolve_launch_command():
    """Resolve the OS command to launch the headless bridge agent."""
    if getattr(sys, "frozen", False):
        return _quote(str(Path(sys.executable).resolve()))

    launcher_sh = ROOT_DIR / "portable_launch_nyx.sh"
    launcher_ps1 = ROOT_DIR / "portable_launch_nyx.ps1"

    if sys.platform == "win32":
        if launcher_ps1.exists():
            ps = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            return f'{_quote(str(ps))} -NoLogo -NoProfile -ExecutionPolicy Bypass -File {_quote(str(launcher_ps1))} -EntryScript bridge_app.py -Quiet -NoOpen'
        pythonw = resolve_python_executable(gui=True)
        if pythonw.exists():
            return f'{_quote(str(pythonw))} {_quote(str(ROOT_DIR / "bridge_app.py"))}'
        python = resolve_python_executable(gui=False)
        if python.exists():
            return f'{_quote(str(python))} {_quote(str(ROOT_DIR / "bridge_app.py"))}'
    else:
        if launcher_sh.exists():
            env = os.environ.copy()
            env["NYXSUITE_NO_TRAY"] = "1"
            env["NYXSUITE_NO_OPEN"] = "1"
            return f"{_quote(str(launcher_sh))} bridge_app.py"
        python = resolve_python_executable(gui=False)
        if python.exists():
            return f'{_quote(str(python))} {_quote(str(ROOT_DIR / "bridge_app.py"))}'

    raise FileNotFoundError("Could not resolve a launch command for the bridge agent.")


def set_launch_on_startup(enabled):
    if sys.platform == "win32":
        _set_windows(enabled)
    elif sys.platform == "darwin":
        _set_macos(enabled)
    elif sys.platform.startswith("linux"):
        _set_linux(enabled)
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")


def is_launch_on_startup():
    if sys.platform == "win32":
        return _is_windows()
    elif sys.platform == "darwin":
        return _is_macos()
    elif sys.platform.startswith("linux"):
        return _is_linux()
    return False


def _set_windows(enabled):
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, LAUNCHER_NAME, 0, winreg.REG_SZ, _resolve_launch_command())
        else:
            try:
                winreg.DeleteValue(key, LAUNCHER_NAME)
            except FileNotFoundError:
                pass


def _is_windows():
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, LAUNCHER_NAME)
            return bool(val)
    except Exception:
        return False


def _set_macos(enabled):
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / "com.nyxsuite.agent.plist"
    if enabled:
        cmd = _resolve_launch_command()
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.nyxsuite.agent</string>
<key>ProgramArguments</key><array><string>/bin/sh</string><string>-c</string><string>{cmd}</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><false/>
<key>EnvironmentVariables</key><dict>
<key>NYXSUITE_NO_TRAY</key><string>1</string>
<key>NYXSUITE_NO_OPEN</key><string>1</string>
</dict>
</dict></plist>
"""
        plist_path.write_text(plist_content, encoding="utf-8")
        os.system(f"launchctl load {_quote(str(plist_path))}")
    else:
        if plist_path.exists():
            os.system(f"launchctl unload {_quote(str(plist_path))}")
            plist_path.unlink(missing_ok=True)


def _is_macos():
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.nyxsuite.agent.plist"
    return plist_path.exists()


def _set_linux(enabled):
    autostart_dir = Path.home() / ".config" / "autostart"
    desktop_path = autostart_dir / "nyxsuite-agent.desktop"
    if enabled:
        cmd = _resolve_launch_command()
        autostart_dir.mkdir(parents=True, exist_ok=True)
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Nyx Suite Bridge
Exec={cmd}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
        desktop_path.write_text(desktop_content, encoding="utf-8")
    else:
        desktop_path.unlink(missing_ok=True)


def _is_linux():
    return (Path.home() / ".config" / "autostart" / "nyxsuite-agent.desktop").exists()
