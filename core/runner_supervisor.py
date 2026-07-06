"""Process supervisor for the Nyx and Nyxify runners.

The bridge owns one :class:`RunnerSupervisor` with a :class:`ManagedRunner` per
product. Each ManagedRunner reuses the exact spawn/stop/PID helpers the legacy
tkinter UIs use (``core/process_utils``), so a runner launched by the bridge is
indistinguishable from one launched by the old UI:

* command = the frozen ``"<Name>.exe"`` when packaged, else ``[python, script]``
* spawned detached via :func:`start_background_process` with per-runner logs
* PID tracked in a pid file, with orphan re-adoption by process name / cmdline
* stop via :func:`stop_process_tree` (``taskkill /T /F`` on Windows)

This module only orchestrates processes; per-task automation logic (account
creation, Bitmoji creation) lives untouched in the runner scripts themselves.
This mirrors ``start_bot_process`` / ``stop_bot_process`` from ``ui_nyx.py`` and
``start_runner_process`` / ``stop_runner_process`` from ``ui_nyxify.py``.
"""

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from core.process_utils import (
    ROOT_DIR,
    clear_pid_file,
    find_process_ids_by_names,
    find_python_process_ids,
    force_kill_process_tree,
    is_pid_running,
    read_pid_file,
    resolve_python_executable,
    start_background_process,
    stop_process_tree,
    write_pid_file,
)

# How long stop() waits for a runner to die after SIGTERM/taskkill before
# escalating to a force kill — keeps the hotkey/dashboard Stop truly total.
STOP_CONFIRM_TIMEOUT_SECONDS = 3.0

ORPHAN_SCAN_TTL_SECONDS = 3.0


@dataclass
class RunnerSpec:
    """Everything the supervisor needs to launch and track one runner."""

    name: str                                   # "nyx" | "nyxify"
    script_path: Path                           # ROOT_DIR/main.py | ROOT_DIR/nyxify_runner.py
    pid_file: Path
    stdout_path: Path
    stderr_path: Path
    script_match: str                           # cmdline substring for orphan detection ("main.py")
    exe_candidates: List[Path] = field(default_factory=list)   # frozen-build exe names, newest first
    process_names: List[str] = field(default_factory=list)     # exe basenames for orphan detection
    env_builder: Optional[Callable[[], dict]] = None           # returns env overrides (db path, flags, config)
    python_executable: Optional[Path] = None    # defaults to resolve_python_executable(gui=False)


class ManagedRunner:
    def __init__(self, spec: RunnerSpec):
        self.spec = spec
        self._pid_cache = {"at": 0.0, "pid": None, "scanning": False}

    def resolve_exe(self) -> Optional[Path]:
        for candidate in self.spec.exe_candidates:
            try:
                if Path(candidate).exists():
                    return Path(candidate)
            except Exception:
                continue
        return None

    def _find_pids(self) -> List[int]:
        pids: List[int] = []
        if self.spec.script_match:
            for pid in find_python_process_ids(self.spec.script_match):
                if pid not in pids:
                    pids.append(pid)
        if self.spec.process_names:
            for pid in find_process_ids_by_names(self.spec.process_names):
                if pid not in pids:
                    pids.append(pid)
        return pids

    def resolve_pid(self) -> Optional[int]:
        # Fast path: a live pid file is authoritative and cheap.
        pid = read_pid_file(self.spec.pid_file)
        if pid and is_pid_running(pid):
            return pid
        if pid:
            clear_pid_file(self.spec.pid_file)
        # No live pid file. The orphan scan shells out to PowerShell (~1-2s), so
        # run it on a background thread and return the cached result immediately,
        # keeping the status/SSE path responsive. A bridge-started runner always
        # writes its pid file, so this path only matters for externally-started
        # (orphan) runners.
        cache = self._pid_cache
        now = time.monotonic()
        if (now - float(cache.get("at") or 0.0)) >= ORPHAN_SCAN_TTL_SECONDS and not cache.get("scanning"):
            cache["scanning"] = True
            threading.Thread(target=self._scan_orphans, daemon=True).start()
        return cache.get("pid")

    def _scan_orphans(self) -> None:
        found = None
        for detected in self._find_pids():
            if is_pid_running(detected):
                found = detected
                break
        if found:
            write_pid_file(self.spec.pid_file, found)
        self._pid_cache.update({"at": time.monotonic(), "pid": found, "scanning": False})

    def is_running(self) -> bool:
        return self.resolve_pid() is not None

    def _build_command(self) -> list:
        exe = self.resolve_exe()
        if getattr(sys, "frozen", False) and exe is not None:
            return [str(exe)]
        python = self.spec.python_executable or resolve_python_executable(gui=False)
        return [str(python), str(self.spec.script_path)]

    def start(self, force_restart: bool = False, extra_env: Optional[dict] = None):
        """Spawn the runner. Returns (pid, started). Mirrors start_bot_process()."""
        live = [pid for pid in self._find_pids() if is_pid_running(pid)]
        existing = read_pid_file(self.spec.pid_file)
        if existing and is_pid_running(existing) and existing not in live:
            live.insert(0, existing)

        if live:
            if force_restart:
                for pid in live:
                    stop_process_tree(pid)
                clear_pid_file(self.spec.pid_file)
            else:
                write_pid_file(self.spec.pid_file, live[0])
                return live[0], False

        env = os.environ.copy()
        if self.spec.env_builder:
            try:
                env.update({k: str(v) for k, v in (self.spec.env_builder() or {}).items()})
            except Exception:
                pass
        if extra_env:
            env.update({k: str(v) for k, v in extra_env.items()})

        process = start_background_process(
            self._build_command(),
            cwd=ROOT_DIR,
            stdout_path=self.spec.stdout_path,
            stderr_path=self.spec.stderr_path,
            env=env,
        )
        write_pid_file(self.spec.pid_file, process.pid)
        return process.pid, True

    def stop(self) -> bool:
        """Kill the runner process tree. Returns True if anything was stopped.

        Confirms every candidate actually died; a runner that survives SIGTERM
        (e.g. wedged inside a blocking GUI/browser call) is force-killed so a
        Stop — from the dashboard button or the global hotkey — is always total."""
        candidates: List[int] = []
        pid = self.resolve_pid()
        if pid:
            candidates.append(pid)
        for live in self._find_pids():
            if live not in candidates:
                candidates.append(live)

        if not candidates:
            clear_pid_file(self.spec.pid_file)
            return False

        stopped = False
        for candidate in candidates:
            try:
                stop_process_tree(candidate)
                stopped = True
            except Exception:
                continue

        deadline = time.monotonic() + STOP_CONFIRM_TIMEOUT_SECONDS
        survivors = [c for c in candidates if is_pid_running(c)]
        while survivors and time.monotonic() < deadline:
            time.sleep(0.15)
            survivors = [c for c in candidates if is_pid_running(c)]
        for survivor in survivors:
            try:
                force_kill_process_tree(survivor)
                stopped = True
            except Exception:
                continue

        clear_pid_file(self.spec.pid_file)
        return stopped

    def restart(self, extra_env: Optional[dict] = None):
        self.stop()
        return self.start(force_restart=True, extra_env=extra_env)


class RunnerSupervisor:
    """Holds one ManagedRunner per product and exposes start/stop/restart/status."""

    def __init__(self):
        self._runners: dict = {}

    def register(self, spec: RunnerSpec) -> ManagedRunner:
        runner = ManagedRunner(spec)
        self._runners[spec.name] = runner
        return runner

    def get(self, name: str) -> Optional[ManagedRunner]:
        return self._runners.get(name)

    def names(self) -> List[str]:
        return list(self._runners.keys())

    def start(self, name: str, **kwargs):
        return self._runners[name].start(**kwargs)

    def stop(self, name: str) -> bool:
        return self._runners[name].stop()

    def restart(self, name: str, **kwargs):
        return self._runners[name].restart(**kwargs)

    def is_running(self, name: str) -> bool:
        runner = self._runners.get(name)
        return bool(runner and runner.is_running())

    def status(self) -> dict:
        return {
            name: {"running": runner.is_running(), "pid": runner.resolve_pid()}
            for name, runner in self._runners.items()
        }
