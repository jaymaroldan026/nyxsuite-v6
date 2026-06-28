"""Headless Nyx controller for the bridge.

Supplies the ``status_provider`` and ``action_handlers`` that
:class:`core.nyx_local_api.NyxLocalApiServer` consumes, with **no tkinter
dependency**. It reuses the same building blocks ``ui_nyx.py`` uses — TaskStore,
AdsPowerManager, nyx_runtime_config, the license summary, ``runner_flags`` and
the :class:`~core.runner_supervisor.RunnerSupervisor` — so behaviour matches the
desktop app. Per-task automation (Bitmoji creation) is untouched; this only
orchestrates the runner process and answers queue/status queries.

Heavy/optional imports (TaskStore, AdsPowerManager, license_manager) are lazy so
this module stays importable in a bare checkout that lacks runtime deps. License
verification uses the committed public key (``core/license_public_key.py``) and
needs no local secret; only code *generation* needs the git-ignored signing key.
"""

import threading
import time

from core import runner_flags
from core.process_utils import APP_DATA_DIR, LOGS_DIR, ROOT_DIR
from core.runner_supervisor import RunnerSpec
from core.version import NYX_VERSION_LABEL

# How long a cached AdsPower profile_id -> name (username) map stays fresh
# before a background refresh is kicked off. Keeps status_snapshot non-blocking.
PROFILE_NAME_CACHE_TTL_SECONDS = 20.0

NYX_DB_PATH = APP_DATA_DIR / "data" / "nyx_tasks.db"
PID_FILE = LOGS_DIR / "bot.pid"
BOT_STDOUT = LOGS_DIR / "bot_ui_stdout.log"
BOT_STDERR = LOGS_DIR / "bot_ui_stderr.log"
BOT_SCRIPT = ROOT_DIR / "main.py"
# v4 ships its own runner exe (named via the version label, e.g. "NyxBot v4.0.0.exe").
# We deliberately do NOT list the v3 exe names, so a running v3 NyxBot is never
# mis-detected as this line's runner.
# macOS frozen builds produce .app bundles or plain executables (no .exe).
BOT_EXECUTABLE_CANDIDATES = [
    ROOT_DIR / f"NyxBot {NYX_VERSION_LABEL}.exe",
    ROOT_DIR / f"NyxBot {NYX_VERSION_LABEL}.app",
    ROOT_DIR / f"NyxBot {NYX_VERSION_LABEL}",
]
BOT_EXECUTABLE_PROCESS_NAMES = [
    f"NyxBot {NYX_VERSION_LABEL}.exe",
    f"NyxBot {NYX_VERSION_LABEL}",
]


def _load_config() -> dict:
    try:
        from core.nyx_runtime_config import load_nyx_config

        return load_nyx_config() or {}
    except Exception:
        return {}


def _license_summary() -> dict:
    try:
        from core.license_manager import get_activation_summary

        return get_activation_summary() or {}
    except Exception:
        return {}


class NyxController:
    """Headless equivalent of the Nyx parts of NyxApp (start/pause/stop/status)."""

    NAME = "nyx"

    def __init__(self, supervisor, store=None, adspower=None):
        if store is None:
            from core.task_store import TaskStore

            store = TaskStore(db_path=NYX_DB_PATH)
        if adspower is None:
            from core.adspower import AdsPowerManager

            adspower = AdsPowerManager()
        self.store = store
        self.adspower = adspower
        self.supervisor = supervisor
        self.runner = supervisor.register(self._spec())
        self._name_cache = {"at": 0.0, "value": {}, "refreshing": False}

    def _spec(self) -> RunnerSpec:
        return RunnerSpec(
            name=self.NAME,
            script_path=BOT_SCRIPT,
            pid_file=PID_FILE,
            stdout_path=BOT_STDOUT,
            stderr_path=BOT_STDERR,
            script_match=str(BOT_SCRIPT),  # full path so v4 never adopts a v3 source runner
            exe_candidates=BOT_EXECUTABLE_CANDIDATES,
            process_names=BOT_EXECUTABLE_PROCESS_NAMES,
            env_builder=self._base_env,
        )

    def _base_env(self) -> dict:
        env = {"TASK_DB_PATH": str(NYX_DB_PATH)}
        env.update(runner_flags.runner_env())
        return env

    def _start_env(self, min_pending_override=None) -> dict:
        config = _load_config()
        min_pending = (
            min_pending_override
            if min_pending_override is not None
            else config.get("pending_threshold", 10)
        )
        return {
            "MIN_PENDING_TO_RUN": str(min_pending),
            "MAX_PARALLEL_PROFILES": str(config.get("max_parallel_profiles", 10)),
        }

    # --------------------------------------------------------------- usernames
    def _profile_names(self) -> dict:
        """Return the cached ``{profile_id: username}`` map, refreshing it in a
        background thread when stale. Never blocks — so the dashboard status/SSE
        path stays responsive even if AdsPower is slow or down."""
        cache = self._name_cache
        now = time.monotonic()
        stale = (now - float(cache.get("at") or 0.0)) >= PROFILE_NAME_CACHE_TTL_SECONDS
        if stale and not cache.get("refreshing"):
            cache["refreshing"] = True
            threading.Thread(target=self._refresh_names, daemon=True).start()
        return cache.get("value") or {}

    def _refresh_names(self):
        value = {}
        try:
            value = self.adspower.get_profile_name_map()
        except Exception:
            value = self._name_cache.get("value") or {}
        self._name_cache.update({"at": time.monotonic(), "value": value, "refreshing": False})

    # ------------------------------------------------------------------ status
    def status_snapshot(self) -> dict:
        tasks = self.store.list_tasks(limit=500)
        name_map = self._profile_names()
        if name_map:
            for row in tasks:
                if not str(row.get("username") or "").strip():
                    row["username"] = name_map.get(str(row.get("profile_id") or "").strip(), "")
        pending = sum(1 for t in tasks if t["status"] == "PENDING")
        running = sum(1 for t in tasks if t["status"] == "RUNNING")
        failed = sum(1 for t in tasks if t["status"] == "FAILED")
        done = sum(1 for t in tasks if t["status"] == "DONE")
        config = _load_config()
        threshold = int(config.get("pending_threshold", 10) or 10)
        pid = self.runner.resolve_pid()
        paused = runner_flags.nyx_is_paused()
        health = runner_flags.nyx_get_health()

        if pid:
            if paused:
                state, detail = "paused", f"Bot paused (PID {pid})"
            elif health:
                # AdsPower env problem is blocking the queue — say so instead of
                # the generic "waiting", so the user knows it's not idle.
                state, detail = "blocked", str(health.get("message") or "AdsPower is blocking the queue.")
            elif running == 0 and pending < threshold:
                state, detail = "waiting", f"Waiting for threshold ({pending}/{threshold}) (PID {pid})"
            else:
                state, detail = "running", f"Bot running in background (PID {pid})"
        elif paused:
            state, detail = "paused", "Bot paused"
        else:
            state, detail = "stopped", "Bot not running"

        return {
            "rows": tasks,
            "counts": {
                "recent": len(tasks),
                "pending": pending,
                "running": running,
                "failed": failed,
                "done": done,
            },
            "bot": {"state": state, "detail": detail, "pid": pid},
            "adspower_health": health,
            "config": config,
            "license": _license_summary(),
        }

    # ---------------------------------------------------------- action handlers
    def start(self, payload=None) -> dict:
        payload = payload or {}
        runner_flags.nyx_set_paused(False)

        reset_failed = payload.get("reset_failed", False) is True
        reset_count = 0
        if reset_failed:
            try:
                reset_count = self.store.reset_failed_tasks()
            except Exception:
                reset_count = 0

        min_override = payload.get("min_pending_override")
        if min_override is None and reset_count > 0:
            min_override = 1

        pid, started = self.supervisor.start(
            self.NAME,
            force_restart=bool(payload.get("force_restart", False)),
            extra_env=self._start_env(min_override),
        )

        if reset_count:
            message = f"Reset {reset_count} failed row(s) to PENDING and started Nyx."
        elif started:
            message = f"Bot started in background (PID {pid})."
        else:
            message = f"Bot already running (PID {pid})."

        return {
            "ok": True,
            "message": message,
            "pid": pid,
            "started": started,
            "reset_failed_count": reset_count,
            "status": self.status_snapshot(),
        }

    def pause(self, payload=None) -> dict:
        runner_flags.nyx_set_paused(True)
        return {
            "ok": True,
            "message": "Nyx paused. Running work may finish, but no new pending rows will start.",
            "status": self.status_snapshot(),
        }

    def resume(self, payload=None) -> dict:
        result = self.start({"reset_failed": False})
        result["message"] = "Nyx resumed."
        return result

    def stop(self, payload=None) -> dict:
        stopped = self.supervisor.stop(self.NAME)
        runner_flags.nyx_set_paused(False)
        return {
            "ok": True,
            "stopped": stopped,
            "message": "Nyx stopped fully." if stopped else "No running Nyx bot process was found.",
            "status": self.status_snapshot(),
        }

    def finish_remaining(self, payload=None) -> dict:
        runner_flags.nyx_request_flush()
        result = self.start({"min_pending_override": 1})
        result["message"] = (
            "Nyx will finish the remaining pending rows even if they are below the normal start threshold."
        )
        return result

    def action_handlers(self) -> dict:
        """The /bot/<action> handlers consumed by NyxLocalApiServer.

        Covers the lifecycle controls plus the store-only and AdsPower-only
        actions the extension popup invokes via ``/bot/<action>`` (reset_stuck,
        clear_completed, close_profile, clear_cache_logs). Many queue actions are
        also served directly by NyxLocalApiServer's /queue/* routes (used by the
        dashboard); these handlers make the popup's buttons work too.
        """
        def handle_set_launch(payload):
            from core.startup import set_launch_on_startup
            enabled = bool((payload or {}).get("enabled", False))
            set_launch_on_startup(enabled)
            return {"ok": True, "enabled": enabled}

        def handle_delete_adspower_profile(payload):
            # Used by the SnapBoard "Replace profile" action: delete the old
            # AdsPower profile. The browser extension handles the SnapBoard-side
            # steps (refresh proxy, Warm Up status, clear AdsPower ID) which also
            # makes Nyxify re-detect and re-queue the row as PENDING.
            profile_id = str((payload or {}).get("profile_id", "")).strip()
            if not profile_id:
                return {"ok": False, "error": "AdsPower profile id is required."}
            try:
                self.adspower.delete_profile(profile_id)
            except Exception as exc:
                return {"ok": False, "error": f"AdsPower delete failed: {exc}"}
            return {"ok": True, "message": f"AdsPower profile {profile_id} deleted."}

        def handle_reset_stuck(payload):
            count = self.store.reset_stuck_tasks()
            return {
                "ok": True,
                "count": count,
                "message": f"Reset {count} stuck Nyx row(s) to PENDING.",
                "status": self.status_snapshot(),
            }

        def handle_clear_completed(payload):
            count = self.store.clear_completed_tasks()
            return {
                "ok": True,
                "count": count,
                "message": f"Cleared {count} completed Nyx row(s).",
                "status": self.status_snapshot(),
            }

        def handle_close_profile(payload):
            profile_id = str((payload or {}).get("profile_id", "")).strip()
            if not profile_id:
                return {"ok": False, "error": "AdsPower profile id is required."}
            try:
                self.adspower.close_profile(profile_id)
            except Exception as exc:
                return {"ok": False, "error": f"Could not close AdsPower profile {profile_id}: {exc}"}
            return {"ok": True, "message": f"Closed AdsPower profile {profile_id}."}

        def handle_clear_cache_logs(payload):
            removed = 0
            try:
                for log_file in LOGS_DIR.glob("*.log"):
                    try:
                        log_file.unlink()
                        removed += 1
                    except Exception:
                        # A log held open by a running process can't be deleted;
                        # truncate it instead so the on-disk size is reclaimed.
                        try:
                            log_file.write_text("", encoding="utf-8")
                        except Exception:
                            pass
            except Exception as exc:
                return {"ok": False, "error": f"Could not clear logs: {exc}"}
            return {"ok": True, "count": removed, "message": f"Cleared {removed} Nyx log file(s)."}

        return {
            "start": self.start,
            "pause": self.pause,
            "resume": self.resume,
            "stop": self.stop,
            "finish_remaining": self.finish_remaining,
            "set_launch_on_startup": handle_set_launch,
            "delete_adspower_profile": handle_delete_adspower_profile,
            "reset_stuck": handle_reset_stuck,
            "clear_completed": handle_clear_completed,
            "close_profile": handle_close_profile,
            "clear_cache_logs": handle_clear_cache_logs,
        }
