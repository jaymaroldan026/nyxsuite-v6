"""Headless Nyxify controller for the bridge.

Headless equivalent of the Nyxify parts of ``ui_nyxify.py``: supplies the
``status_provider`` and ``action_handlers`` that
:class:`core.nyxify_local_api.NyxifyLocalApiServer` consumes, with no tkinter
dependency. Reuses NyxifyTaskStore, AdsPowerManager, nyxify_runtime_config,
``runner_flags`` and the :class:`~core.runner_supervisor.RunnerSupervisor`.
Account-creation/signup automation is untouched; this only orchestrates the
runner process and answers queue/status queries.
"""

import threading
import time

from core import runner_flags
from core.process_utils import APP_DATA_DIR, LOGS_DIR, ROOT_DIR
from core.runner_supervisor import RunnerSpec
from core.version import NYXIFY_VERSION_LABEL

NYXIFY_DB_PATH = APP_DATA_DIR / "data" / "nyxify_tasks.db"
PID_FILE = LOGS_DIR / "nyxify_runner.pid"
RUNNER_STDOUT = LOGS_DIR / "nyxify_runner_stdout.log"
RUNNER_STDERR = LOGS_DIR / "nyxify_runner_stderr.log"
RUNNER_SCRIPT = ROOT_DIR / "nyxify_runner.py"
# v4 ships its own runner exe; no v3 names, for isolation (see nyx_controller).
# macOS frozen builds produce .app bundles or plain executables (no .exe).
RUNNER_EXECUTABLE_CANDIDATES = [
    ROOT_DIR / f"NyxifyRunner {NYXIFY_VERSION_LABEL}.exe",
    ROOT_DIR / f"NyxifyRunner {NYXIFY_VERSION_LABEL}.app",
    ROOT_DIR / f"NyxifyRunner {NYXIFY_VERSION_LABEL}",
]
RUNNER_EXECUTABLE_PROCESS_NAMES = [
    f"NyxifyRunner {NYXIFY_VERSION_LABEL}.exe",
    f"NyxifyRunner {NYXIFY_VERSION_LABEL}",
]
ADSPOWER_USAGE_CACHE_TTL_SECONDS = 8.0


def _load_config() -> dict:
    try:
        from core.nyxify_runtime_config import load_nyxify_config

        return load_nyxify_config() or {}
    except Exception:
        return {}


class NyxifyController:
    """Headless equivalent of the Nyxify parts of NyxifyApp."""

    NAME = "nyxify"

    def __init__(self, supervisor, store=None, adspower=None):
        if store is None:
            from core.nyxify_task_store import NyxifyTaskStore

            store = NyxifyTaskStore(db_path=NYXIFY_DB_PATH)
        if adspower is None:
            from core.adspower import AdsPowerManager

            adspower = AdsPowerManager()
        self.store = store
        self.adspower = adspower
        self.supervisor = supervisor
        self.runner = supervisor.register(self._spec())
        self._usage_cache = {"at": 0.0, "value": None, "error": "", "refreshing": False}

    def _spec(self) -> RunnerSpec:
        return RunnerSpec(
            name=self.NAME,
            script_path=RUNNER_SCRIPT,
            pid_file=PID_FILE,
            stdout_path=RUNNER_STDOUT,
            stderr_path=RUNNER_STDERR,
            script_match=str(RUNNER_SCRIPT),  # full path so v4 never adopts a v3 source runner
            exe_candidates=RUNNER_EXECUTABLE_CANDIDATES,
            process_names=RUNNER_EXECUTABLE_PROCESS_NAMES,
            env_builder=self._base_env,
        )

    def _base_env(self) -> dict:
        return {
            "NYXIFY_TASK_DB_PATH": str(NYXIFY_DB_PATH),
            "NYXIFY_PAUSE_FILE": str(runner_flags.NYXIFY_PAUSE_FILE),
        }

    def _adspower_usage(self):
        """Return the cached AdsPower profile count immediately, refreshing in a
        background thread when stale. Never blocks the caller — so the dashboard
        status/SSE path stays responsive even if AdsPower is slow or down."""
        cache = self._usage_cache
        now = time.monotonic()
        stale = (now - float(cache.get("at") or 0.0)) >= ADSPOWER_USAGE_CACHE_TTL_SECONDS
        if stale and not cache.get("refreshing"):
            cache["refreshing"] = True
            threading.Thread(target=self._refresh_usage, daemon=True).start()
        return cache.get("value"), str(cache.get("error") or "")

    def _refresh_usage(self):
        used, error = None, ""
        try:
            used = self.adspower.get_profile_count()
        except Exception as exc:
            error = str(exc)
        self._usage_cache.update(
            {"at": time.monotonic(), "value": used, "error": error, "refreshing": False}
        )

    # ------------------------------------------------------------------ status
    def status_snapshot(self) -> dict:
        tasks = self.store.list_tasks(limit=500)
        pending = sum(1 for r in tasks if r["status"] == "PENDING")
        waiting = sum(
            1
            for r in tasks
            if r["status"] == "PENDING" and str(r.get("last_step", "")).startswith("waiting_for_")
        )
        running = sum(1 for r in tasks if r["status"] == "RUNNING")
        failed = sum(1 for r in tasks if r["status"] == "FAILED")
        done = sum(1 for r in tasks if r["status"] == "DONE")
        used_profiles, usage_error = self._adspower_usage()

        pid = self.runner.resolve_pid()
        paused = runner_flags.nyxify_is_paused()
        if paused:
            state = "PAUSED"
            detail = f"Nyxify runner is paused (PID {pid})." if pid else "Nyxify runner is paused."
        elif pid:
            state, detail = "RUNNING", "Nyxify runner is active."
        else:
            state, detail = "STOPPED", "Nyxify runner is not running."

        return {
            "rows": tasks,
            "counts": {
                "pending": pending,
                "waiting": waiting,
                "ready": max(0, pending - waiting),
                "running": running,
                "failed": failed,
                "done": done,
                "recent": len(tasks),
            },
            "bot": {"state": state, "detail": detail, "pid": pid if pid else None},
            "adspower_usage": {"used": used_profiles, "error": usage_error},
            "config": _load_config(),
        }

    # ---------------------------------------------------------- action handlers
    def start(self, payload=None) -> dict:
        runner_flags.nyxify_set_paused(False)
        pid, started = self.supervisor.start(
            self.NAME, force_restart=bool((payload or {}).get("force_restart", False))
        )
        return {
            "ok": True,
            "message": f"Nyxify runner started (PID {pid})." if started else f"Nyxify runner already running (PID {pid}).",
            "status": self.status_snapshot(),
        }

    def pause(self, payload=None) -> dict:
        runner_flags.nyxify_set_paused(True)
        return {"ok": True, "message": "Nyxify runner paused.", "status": self.status_snapshot()}

    def resume(self, payload=None) -> dict:
        runner_flags.nyxify_set_paused(False)
        pid, _started = self.supervisor.start(self.NAME, force_restart=False)
        return {"ok": True, "message": f"Nyxify runner resumed (PID {pid}).", "status": self.status_snapshot()}

    def stop(self, payload=None) -> dict:
        stopped = self.supervisor.stop(self.NAME)
        runner_flags.nyxify_set_paused(False)
        return {
            "ok": True,
            "message": "Nyxify runner stopped." if stopped else "No Nyxify runner process was found.",
            "status": self.status_snapshot(),
        }

    def reset_failed(self, payload=None) -> dict:
        count = self.store.reset_failed_tasks()
        return {"ok": True, "count": count, "message": f"Reset {count} failed Nyxify row(s).", "status": self.status_snapshot()}

    def clear_queue(self, payload=None) -> dict:
        count = self.store.clear_all_tasks()
        return {"ok": True, "count": count, "message": f"Cleared {count} Nyxify row(s).", "status": self.status_snapshot()}

    def action_handlers(self) -> dict:
        """The /bot/<action> handlers consumed by NyxifyLocalApiServer.

        Lifecycle + reset/clear are implemented here. delete_orphan_failed_profiles
        and rename_profile (which need AdsPower cleanup helpers) are layered on in
        Phase 3 with the dashboard controls that use them.
        """
        return {
            "start": self.start,
            "pause": self.pause,
            "resume": self.resume,
            "stop": self.stop,
            "reset_failed": self.reset_failed,
            "clear_queue": self.clear_queue,
        }
