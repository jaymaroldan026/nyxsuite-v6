"""Nyx Suite bridge — one tray app for the whole suite.

A single lightweight process that:
  * holds a single-instance guard (RunnerLock on :8869)
  * owns one shared AdsPowerManager
  * supervises the Nyx and Nyxify runner subprocesses (RunnerSupervisor +
    NyxController / NyxifyController) — per-task automation is untouched
  * hosts the attach-aware product local APIs (Nyx :8865, Nyxify :8866)
  * serves the web dashboard (:8870) + /bridge/* actions
  * shows a pystray tray (Open Dashboard, per-product Start/Stop/Restart,
    Check Update, Roll back, Exit). The tray is best-effort: if pystray/PIL are
    unavailable the bridge still runs headless and serves the dashboard.

Run from source:  python bridge_app.py
Installed:        launched by the "Nyx Suite" tray exe / Start-Menu shortcut.

Closing the bridge does NOT stop the runners (same as the old UI's behaviour);
use the tray/dashboard Stop to halt a runner.
"""

import os
import socket
import sys
import threading
import webbrowser

from pathlib import Path

from core.agent_token import get_or_create_token
from core.process_utils import ensure_logs_dir
from core.runner_lock import RunnerLock
from core.runner_supervisor import RunnerSupervisor
from core.webui_server import WebDashboardServer

SINGLE_INSTANCE_PORT = int(os.getenv("NYXSUITE_BRIDGE_PORT", "8869"))
NYX_API_PORT = int(os.getenv("NYX_LOCAL_API_PORT", "8865"))
NYXIFY_API_PORT = int(os.getenv("NYXIFY_LOCAL_API_PORT", "8866"))
DASHBOARD_PORT = int(os.getenv("NYXSUITE_DASHBOARD_PORT", "8870"))
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}/"


def log(message: str) -> None:
    try:
        from core.logger import logger

        logger.info(message)
    except Exception:
        print(f"[bridge] {message}", flush=True)


def _ensure_data_dirs():
    """Create all expected data subdirectories on first launch."""
    from core.process_utils import ROOT_DIR
    data_dir = ROOT_DIR / "data"
    for sub in ("full_auto_usernames", "signup_names", "logs", "cache", "updates", "templates"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)


def _port_in_use(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        return sock.connect_ex((host, int(port))) == 0
    except OSError:
        return False
    finally:
        sock.close()


class BridgeApp:
    def __init__(self):
        self.supervisor = RunnerSupervisor()
        self.adspower = None
        self.nyx = None
        self.nyxify = None
        self.nyx_api = None
        self.nyxify_api = None
        self.dashboard = None
        self._tray_icon = None
        self._stop = threading.Event()
        self.token = ""

    # ------------------------------------------------------------------ build
    def _version(self) -> str:
        try:
            from core.version import NYX_VERSION

            return NYX_VERSION
        except Exception:
            return ""

    def build(self):
        _ensure_data_dirs()
        from core.adspower import AdsPowerManager
        from core.nyx_controller import NyxController
        from core.nyxify_controller import NyxifyController

        # Per-install token required on state-changing endpoints (env can override).
        self.token = os.getenv("NYXSUITE_TOKEN") or get_or_create_token()
        self.adspower = AdsPowerManager()
        self.nyx = NyxController(self.supervisor, adspower=self.adspower)
        self.nyxify = NyxifyController(self.supervisor, adspower=self.adspower)
        pass

    def start_servers(self):
        from core.nyx_local_api import NyxLocalApiServer
        from core.nyxify_local_api import NyxifyLocalApiServer

        # Attach-aware: if a legacy tkinter UI already holds the product port,
        # do NOT re-bind — the dashboard talks to the already-running server.
        if _port_in_use("127.0.0.1", NYX_API_PORT):
            log(f"Nyx API :{NYX_API_PORT} already in use — attach mode (using existing server).")
        else:
            self.nyx_api = NyxLocalApiServer(
                self.nyx.store,
                host="127.0.0.1",
                port=NYX_API_PORT,
                token=os.getenv("NYX_LOCAL_API_TOKEN") or self.token,
                status_provider=self.nyx.status_snapshot,
                action_handlers=self.nyx.action_handlers(),
            )
            self.nyx_api.start()
            log(f"Nyx local API on :{NYX_API_PORT}")

        if _port_in_use("127.0.0.1", NYXIFY_API_PORT):
            log(f"Nyxify API :{NYXIFY_API_PORT} already in use — attach mode (using existing server).")
        else:
            self.nyxify_api = NyxifyLocalApiServer(
                self.nyxify.store,
                host="127.0.0.1",
                port=NYXIFY_API_PORT,
                token=os.getenv("NYXIFY_LOCAL_API_TOKEN") or self.token,
                status_provider=self.nyxify.status_snapshot,
                action_handlers=self.nyxify.action_handlers(),
            )
            self.nyxify_api.start()
            log(f"Nyxify local API on :{NYXIFY_API_PORT}")

        self.dashboard = WebDashboardServer(
            controllers={"nyx": self.nyx, "nyxify": self.nyxify},
            host="127.0.0.1",
            port=DASHBOARD_PORT,
            bridge_actions=self._bridge_actions(),
            version=self._version(),
            token=self.token,
        )
        self.dashboard.start()
        log(f"Dashboard on {DASHBOARD_URL}")
        # NOTE: the Ctrl+F8 pause/resume hotkey is started inside each runner
        # process (main.py / nyxify_runner.py), not here — the listener belongs in
        # the process doing the work so it pauses the *current* run, and so the
        # two runners toggle their own pause flags without cancelling each other.

    def _bridge_actions(self) -> dict:
        return {
            "check_update": self._action_check_update,
            "apply_update": self._action_apply_update,
            "rollback": self._action_rollback,
            "list_backups": self._action_list_backups,

            "autostart": self._action_autostart,
            "set_autostart": self._action_set_autostart,
            "install_deps": self._action_install_deps,
            "install_deps_status": self._action_install_deps_status,
            "sync_extensions": self._action_sync_extensions,
            "adspower_test": self._action_adspower_test,
            "shutdown": self._action_shutdown,
        }

    def _action_adspower_test(self, payload=None) -> dict:
        """Run the AdsPower preflight probe with the currently-saved settings so
        the dashboard's "Test AdsPower connection" button can show OK or the
        actionable permission/unreachable error inline."""
        try:
            from core.adspower import AdsPowerManager
            result = AdsPowerManager().preflight_check()
            return {
                "ok": bool(result.get("ok")),
                "code": result.get("code"),
                "message": result.get("message"),
            }
        except Exception as exc:
            return {"ok": False, "code": "error", "message": f"AdsPower test failed: {exc}"}

    def _action_shutdown(self, payload=None) -> dict:
        log("Shutdown requested via bridge action.")
        threading.Thread(target=self._request_exit, daemon=True).start()
        return {"ok": True, "message": "Bridge shutting down."}

    def _action_check_update(self, payload=None) -> dict:
        try:
            from core.release_updater import (compare_versions, get_current_version,
                                              get_latest_release, load_update_config,
                                              _trim_release_notes)
        except Exception as exc:
            return {"ok": False, "message": f"Updater unavailable: {exc}"}
        cfg = load_update_config()
        repo, pattern = cfg.get("repo"), cfg.get("asset_pattern")
        current = get_current_version()
        if not repo or not pattern:
            return {"ok": False, "current": current, "message": "Update channel not configured (running from source)."}
        try:
            rel = get_latest_release(repo, pattern)
        except Exception as exc:
            return {"ok": False, "current": current, "message": f"Update check failed: {exc}"}
        available = compare_versions(current, rel.tag_name) < 0
        return {
            "ok": True,
            "current": current,
            "latest": rel.tag_name,
            "latest_name": rel.release_name or rel.tag_name,
            "update_available": available,
            "release_notes": _trim_release_notes(rel.body) if available else "",
            "release_url": rel.html_url or "",
            "message": (f"Update {rel.tag_name} available (current {current})." if available
                        else f"Up to date ({current})."),
        }

    def _action_apply_update(self, payload=None) -> dict:
        try:
            from core.release_updater import (apply_update_direct,
                                              get_latest_release, load_update_config)
            from core.release_updater import _log as _update_log
        except Exception as exc:
            return {"ok": False, "message": f"Updater unavailable: {exc}"}
        cfg = load_update_config()
        repo, pattern = cfg.get("repo"), cfg.get("asset_pattern")
        if not repo or not pattern:
            return {"ok": False, "message": "Update channel not configured (running from source)."}
        try:
            rel = get_latest_release(repo, pattern)
            _update_log(f"update started — {rel.tag_name}")
            # Stop runners before update.
            for name in self.supervisor.names():
                try:
                    self.supervisor.stop(name)
                except Exception:
                    pass
            result = apply_update_direct(rel.asset_url, rel.tag_name)
            if not result.get("ok"):
                _update_log(f"direct update failed: {result.get('message')}", "error")
                return {"ok": False, "message": result.get("message", "Update failed.")}
            _update_log(f"update completed — {result.get('message')}")
            self._relaunch_after_exit()
            threading.Timer(0.8, self._request_exit).start()
            return {"ok": True, "message": result.get("message", f"Updated to {rel.tag_name}.")}
        except Exception as exc:
            _update_log(f"update failed: {exc}", "error")
            return {"ok": False, "message": f"Update failed: {exc}"}

    def _action_rollback(self, payload=None) -> dict:
        try:
            from core.release_updater import sync_extensions, sync_source_dirs, _sync_root_files
            from core.update_backup import list_backups, backups_dir
            from core.process_utils import ROOT_DIR
        except Exception as exc:
            return {"ok": False, "message": f"Rollback unavailable: {exc}"}
        backups = list_backups()
        version = (payload or {}).get("version") or (backups[0] if backups else None)
        if not version:
            return {"ok": False, "message": "No backup available to roll back to."}
        try:
            for name in self.supervisor.names():
                try:
                    self.supervisor.stop(name)
                except Exception:
                    pass
            backup_folder = backups_dir() / version
            if not backup_folder.is_dir():
                return {"ok": False, "message": f"Backup folder not found for {version}."}
            # Restore source directories
            sync_source_dirs(backup_folder, ROOT_DIR)
            # Restore extensions
            sync_extensions(backup_folder, ROOT_DIR)
            # Restore root-level files
            _sync_root_files(backup_folder, ROOT_DIR)
            # Restore VERSION
            ver_src = backup_folder / "VERSION"
            if ver_src.exists():
                (ROOT_DIR / "VERSION").write_text(ver_src.read_text(encoding="utf-8-sig"), encoding="ascii")
        except Exception as exc:
            return {"ok": False, "message": f"Rollback failed: {exc}"}
        self._relaunch_after_exit()
        threading.Timer(0.8, self._request_exit).start()
        return {"ok": True, "message": f"Rolling back to {version}; the app will restart."}

    def _action_list_backups(self, payload=None) -> dict:
        try:
            from core.update_backup import list_backups

            return {"ok": True, "backups": list_backups()}
        except Exception as exc:
            return {"ok": False, "backups": [], "message": str(exc)}

    def _action_autostart(self, payload=None) -> dict:
        try:
            from core.startup import is_launch_on_startup

            return {"ok": True, "enabled": is_launch_on_startup()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _action_set_autostart(self, payload=None) -> dict:
        enabled = bool((payload or {}).get("enabled", False))
        try:
            from core.startup import set_launch_on_startup

            set_launch_on_startup(enabled)
            return {"ok": True, "enabled": enabled, "message": f"Start on login {'enabled' if enabled else 'disabled'}."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    _install_deps_status = {"state": "idle", "output": ""}

    def _action_install_deps(self, payload=None) -> dict:
        if self._install_deps_status["state"] == "running":
            return {"ok": False, "message": "Already installing."}
        self._install_deps_status = {"state": "running", "output": ""}
        threading.Thread(target=self._run_install_deps, daemon=True).start()
        return {"ok": True, "message": "Install started. Check status endpoint for progress."}

    def _action_install_deps_status(self, payload=None) -> dict:
        return {"ok": True, **self._install_deps_status}

    def _run_install_deps(self):
        import subprocess, sys
        from pathlib import Path
        from core.process_utils import ROOT_DIR, resolve_python_executable
        python = resolve_python_executable(gui=False)
        req = ROOT_DIR / "requirements.txt"
        output_lines = [f"Using python: {python}"]
        failures = 0
        def run(cmd, label):
            nonlocal failures
            output_lines.append(f">>> {label}...")
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=ROOT_DIR)
                if r.stdout: output_lines.append(r.stdout.strip())
                if r.stderr: output_lines.append(r.stderr.strip())
                if r.returncode == 0:
                    output_lines.append(f"OK: {label}")
                else:
                    output_lines.append(f"FAILED (code {r.returncode}): {label}")
                    failures += 1
            except subprocess.TimeoutExpired:
                output_lines.append(f"TIMEOUT: {label}")
                failures += 1
            except Exception as e:
                output_lines.append(f"ERROR: {label}: {e}")
                failures += 1
        run([str(python), "-m", "pip", "install", "-r", str(req)], "pip install requirements")
        run([str(python), "-m", "playwright", "install", "chromium"], "playwright install chromium")
        state = "done" if failures == 0 else "failed"
        self._install_deps_status = {"state": state, "output": "\n".join(output_lines)}

    def _action_sync_extensions(self, payload=None) -> dict:
        """Sync extension directories from a user-specified source folder
        (or from ROOT_DIR by default) into the install root so the bridge
        always serves the latest extension code.

        Payload may contain:
            source_dir (str): path to a release folder containing nyx_extension/
                              and/or nyxify_extension/.  If omitted, ROOT_DIR is
                              used (the current install root).
        """
        import shutil
        from core.process_utils import ROOT_DIR
        source = (payload or {}).get("source_dir", "").strip()
        source_path = Path(source).resolve() if source else ROOT_DIR
        if not source_path.is_dir():
            return {"ok": False, "message": f"Source folder does not exist: {source_path}"}
        install_root = ROOT_DIR
        synced = []
        errors = []
        for ext_name in ("nyx_extension", "nyxify_extension"):
            src = source_path / ext_name
            if not src.is_dir():
                errors.append(f"{ext_name}: not found in {source_path}")
                continue
            dest = install_root / ext_name
            try:
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                synced.append(ext_name)
                log(f"Synced {ext_name} from {src} to {dest}")
            except Exception as exc:
                errors.append(f"{ext_name}: {exc}")
        message_parts = []
        if synced:
            message_parts.append(f"Synced: {', '.join(synced)}")
        if errors:
            message_parts.append(f"Errors: {'; '.join(errors)}")
        return {
            "ok": len(synced) > 0,
            "synced": synced,
            "errors": errors,
            "message": ". ".join(message_parts) or "No extensions synced.",
        }

    def _relaunch_after_exit(self, delay: float = 3.0):
        """Best-effort relaunch of the bridge after this instance exits.

        Source installs are launched by a one-shot launcher that does NOT
        auto-restart, so after an update/rollback the app would simply vanish
        and look broken. We spawn a detached helper that waits for this process
        to exit (releasing the single-instance lock on :8869) and relaunches
        ``bridge_app.py``. Frozen builds are relaunched by the sidecar instead.
        """
        import subprocess
        import sys

        if getattr(sys, "frozen", False):
            return
        try:
            from core.process_utils import ROOT_DIR, resolve_python_executable

            python = str(resolve_python_executable(gui=(os.name == "nt")))
            bridge = str(ROOT_DIR / "bridge_app.py")
            code = (
                "import time, subprocess; "
                f"time.sleep({float(delay)}); "
                f"subprocess.Popen([{python!r}, {bridge!r}], cwd={str(ROOT_DIR)!r}, close_fds=True)"
            )
            kwargs = {"cwd": str(ROOT_DIR), "close_fds": True}
            if os.name == "nt":
                kwargs["creationflags"] = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                )
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([python, "-c", code], **kwargs)
            log("Scheduled bridge relaunch after exit.")
        except Exception as exc:
            log(f"Relaunch scheduling failed (relaunch manually): {exc}")

    def _request_exit(self):
        """Stop servers and end the process so the sidecar can swap files."""
        self.shutdown()
        icon = self._tray_icon
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        self._stop.set()

    # ------------------------------------------------------------------ tray
    def open_dashboard(self, *args):
        try:
            webbrowser.open(DASHBOARD_URL)
        except Exception as exc:
            log(f"Could not open dashboard: {exc}")

    def _safe(self, fn, label):
        try:
            fn()
            log(f"{label}: ok")
        except Exception as exc:
            log(f"{label} failed: {exc}")

    def run(self):
        """Show the tray (blocking) or fall back to a headless wait loop."""
        icon = self._build_tray_icon()
        if icon is None:
            log("Tray unavailable (pystray/PIL missing) — running headless. Ctrl+C to exit.")
            # Do NOT auto-open the dashboard — it opens only on demand (extension
            # "Open Dashboard" button or tray). Opt in with NYXSUITE_OPEN_ON_START=1.
            if os.getenv("NYXSUITE_OPEN_ON_START") == "1":
                self.open_dashboard()
            try:
                while not self._stop.is_set():
                    self._stop.wait(1.0)
            except KeyboardInterrupt:
                pass
            return
        self._tray_icon = icon
        # macOS: show only the menu-bar icon, never a Python rocket in the Dock.
        self._hide_macos_dock()
        # Dashboard opens only on demand (extension button / tray "Open Dashboard").
        if os.getenv("NYXSUITE_OPEN_ON_START") == "1":
            self.open_dashboard()
        icon.run()  # blocking until icon.stop()

    def _hide_macos_dock(self):
        """Hide the Dock icon on macOS so only the menu-bar tray icon shows.

        pystray creates an NSApplication for the status-bar item but leaves the
        default (regular) activation policy, which puts a Python rocket in the
        Dock. Switching to the Accessory policy (the menu-bar-app pattern)
        removes the Dock icon while keeping the menu-bar icon. No-op elsewhere.
        """
        if sys.platform != "darwin":
            return
        try:
            import AppKit

            policy = getattr(AppKit, "NSApplicationActivationPolicyAccessory", 1)
            AppKit.NSApplication.sharedApplication().setActivationPolicy_(policy)
        except Exception as exc:
            log(f"Could not hide macOS dock icon: {exc}")

    def _build_tray_icon(self):
        if os.getenv("NYXSUITE_NO_TRAY") == "1":
            return None  # headless/server mode: serve the dashboard without a tray icon
        try:
            import pystray
            from core.ui_shared import load_tray_image
        except Exception:
            return None
        image = None
        try:
            image = load_tray_image()
        except Exception:
            image = None
        if image is None:
            return None

        def item(label, fn):
            return pystray.MenuItem(label, lambda icon, _it=None: self._safe(fn, label))

        def product_menu(controller, name):
            return pystray.MenuItem(
                name,
                pystray.Menu(
                    item("Start", lambda: controller.start({})),
                    item("Stop", lambda: controller.stop({})),
                    item("Restart", lambda: (controller.stop({}), controller.start({"force_restart": True}))),
                ),
            )

        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", lambda icon, _it=None: self.open_dashboard()),
            pystray.Menu.SEPARATOR,
            product_menu(self.nyx, "Nyx"),
            product_menu(self.nyxify, "Nyxify"),
            pystray.Menu.SEPARATOR,
            item("Check for Update", lambda: self._bridge_actions()["check_update"]()),
            item("Roll back to previous", lambda: self._bridge_actions()["rollback"]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        return pystray.Icon("nyx_suite", image, "Nyx Suite", menu)

    def _on_exit(self, icon=None, item=None):
        log("Bridge exiting (runners left running).")
        self.shutdown()
        if icon is not None:
            icon.stop()
        self._stop.set()

    def shutdown(self):
        for server in (self.dashboard, self.nyx_api, self.nyxify_api):
            try:
                if server is not None:
                    server.stop()
            except Exception:
                pass


def main():
    ensure_logs_dir()

    # Auto-register the native messaging host so browser extensions can connect.
    try:
        from agent_host.install_host import register
        register()
    except Exception as exc:
        log(f"Native messaging host registration skipped: {exc}")

    guard = RunnerLock("127.0.0.1", SINGLE_INSTANCE_PORT)
    if not guard.acquire():
        log(f"Another Nyx Suite bridge already holds :{SINGLE_INSTANCE_PORT}. Opening the dashboard instead.")
        try:
            webbrowser.open(DASHBOARD_URL)
        except Exception:
            pass
        return
    try:
        # Post-update launch watchdog: if the new build has been crash-looping,
        # roll back to the previous version and exit so the sidecar relaunches it.
        try:
            from core.update_backup import confirm_or_rollback

            verdict = confirm_or_rollback()
            if verdict and verdict[0] == "rollback":
                log("Update failed verification repeatedly — rolled back to the previous version; exiting for the sidecar to relaunch it.")
                return
        except Exception as exc:
            log(f"update watchdog skipped: {exc}")

        app = BridgeApp()
        app.build()
        app.start_servers()
        log("Nyx Suite bridge ready.")
        app.run()
    finally:
        guard.release()


if __name__ == "__main__":
    main()
