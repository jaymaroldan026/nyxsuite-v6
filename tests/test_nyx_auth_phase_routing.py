"""Tests for how the Nyx runner routes auth-phase terminal results.

A banned account (Snapchat "Authorization Error") and a profile proxy failure
("No internet / ERR_PROXY_CONNECTION_FAILED") must each mark the row FAILED with
a step that names the error, so the AdsPower profile is closed and the runner
moves straight to the next account.
"""

import asyncio
import unittest
from unittest import mock

from core import task_runner


class _FakeStore:
    def __init__(self):
        self.status_calls = []

    def begin_run(self, task_id, run_token, step=""):
        return True

    def update_last_step(self, task_id, step, run_token=None):
        return True

    def is_current_run(self, task_id, run_token):
        return True

    def update_status(self, task_id, status, step, error=None, run_token=None):
        self.status_calls.append({"status": status, "step": step, "error": error})
        return True


class _FakeLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def _run(last_result):
    store = _FakeStore()
    task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}

    async def fake_run_profile_task(*args, **kwargs):
        return (False, last_result)

    with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
         mock.patch.object(task_runner, "_get_nyxify_hold_reason", lambda profile_id: ""):
        asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))
    return store


class AuthPhaseRoutingTests(unittest.TestCase):
    def test_proxy_error_marks_failed_with_proxy_error_step(self):
        store = _run("proxy_error")
        self.assertEqual(len(store.status_calls), 1)
        call = store.status_calls[0]
        self.assertEqual(call["status"], "FAILED")
        self.assertEqual(call["step"], "proxy_error")

    def test_banned_snap_marks_failed_with_banned_step(self):
        with mock.patch("core.snapboard_status.mark_account_banned", lambda *a, **k: None):
            store = _run("banned_snap")
        self.assertEqual(len(store.status_calls), 1)
        call = store.status_calls[0]
        self.assertEqual(call["status"], "FAILED")
        self.assertEqual(call["step"], "banned_snap")

    def test_manual_terminate_marks_failed_with_manual_step(self):
        store = _run("manual_terminate")
        self.assertEqual(len(store.status_calls), 1)
        call = store.status_calls[0]
        self.assertEqual(call["status"], "FAILED")
        self.assertEqual(call["step"], "manual_terminate")


if __name__ == "__main__":
    unittest.main()
