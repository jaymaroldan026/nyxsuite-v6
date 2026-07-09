"""Runner supervisor must never trust or kill a recycled pid-file PID.

Windows (and, less often, POSIX) recycle PIDs. A pid file left by a previous
session can point at a number the OS has since handed to an unrelated process —
commonly ``chrome.exe``. Before v6.0.7 ``resolve_pid`` treated any live PID in
the pid file as authoritative and ``stop()`` would run ``taskkill /PID <pid>
/T /F`` on it, tree-killing the user's Chrome. ``pid_matches`` now confirms the
PID's image/cmdline first, and ``ManagedRunner`` fails closed when it can't.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import process_utils
from core.runner_supervisor import ManagedRunner, RunnerSpec


def _spec(tmp: Path) -> RunnerSpec:
    return RunnerSpec(
        name="nyx",
        script_path=Path("/app/main.py"),
        pid_file=tmp / "nyx.pid",
        stdout_path=tmp / "out.log",
        stderr_path=tmp / "err.log",
        script_match="/app/main.py",
        process_names=["NyxBot 6.0.6.exe", "NyxBot 6.0.6"],
    )


class PidMatchesTests(unittest.TestCase):
    def test_matches_by_cmdline_substring(self):
        with mock.patch.object(
            process_utils, "_process_identity",
            return_value=("python.exe", r"c:\venv\python.exe /app/main.py"),
        ):
            self.assertTrue(
                process_utils.pid_matches(1234, ["NyxBot 6.0.6.exe"], "/app/main.py")
            )

    def test_matches_by_image_name_case_insensitive(self):
        with mock.patch.object(
            process_utils, "_process_identity",
            return_value=("nyxbot 6.0.6.exe", "nyxbot 6.0.6.exe --run"),
        ):
            self.assertTrue(
                process_utils.pid_matches(1234, ["NyxBot 6.0.6.exe"], "/app/main.py")
            )

    def test_recycled_chrome_pid_does_not_match(self):
        with mock.patch.object(
            process_utils, "_process_identity",
            return_value=("chrome.exe", r"c:\program files\google\chrome\chrome.exe --type=renderer"),
        ):
            self.assertFalse(
                process_utils.pid_matches(1234, ["NyxBot 6.0.6.exe"], "/app/main.py")
            )

    def test_unreadable_identity_fails_closed(self):
        with mock.patch.object(process_utils, "_process_identity", return_value=("", "")):
            self.assertFalse(
                process_utils.pid_matches(1234, ["NyxBot 6.0.6.exe"], "/app/main.py")
            )

    def test_no_criteria_never_matches(self):
        with mock.patch.object(
            process_utils, "_process_identity", return_value=("python.exe", "anything")
        ):
            self.assertFalse(process_utils.pid_matches(1234, [], ""))


class ManagedRunnerGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.runner = ManagedRunner(_spec(self.tmp))
        self.pid_file = self.tmp / "nyx.pid"

    def test_resolve_pid_ignores_recycled_pidfile_pid(self):
        self.pid_file.write_text("4321")
        with mock.patch("core.runner_supervisor.is_pid_running", return_value=True), \
             mock.patch("core.runner_supervisor.pid_matches", return_value=False), \
             mock.patch.object(self.runner, "_scan_orphans"):
            # Recycled PID: alive but not ours -> not returned, pid file dropped.
            self.assertIsNone(self.runner.resolve_pid())
        self.assertFalse(self.pid_file.exists())

    def test_resolve_pid_trusts_matching_pid(self):
        self.pid_file.write_text("4321")
        with mock.patch("core.runner_supervisor.is_pid_running", return_value=True), \
             mock.patch("core.runner_supervisor.pid_matches", return_value=True):
            self.assertEqual(self.runner.resolve_pid(), 4321)

    def test_spawned_pid_trusted_without_identity_lookup(self):
        self.runner._spawned_pids.add(999)
        with mock.patch(
            "core.runner_supervisor.pid_matches",
            side_effect=AssertionError("pid_matches must not run for a PID we spawned"),
        ):
            self.assertTrue(self.runner._pid_is_ours(999))

    def test_identity_verdict_is_cached(self):
        with mock.patch("core.runner_supervisor.pid_matches", return_value=True) as pm:
            self.assertTrue(self.runner._pid_is_ours(555))
            self.assertTrue(self.runner._pid_is_ours(555))
            pm.assert_called_once()  # second call served from cache


if __name__ == "__main__":
    unittest.main()
