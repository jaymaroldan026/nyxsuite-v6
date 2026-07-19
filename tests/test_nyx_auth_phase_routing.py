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
from core.adspower import AdsPowerProfileNotOpenError


class _FakeStore:
    def __init__(self):
        self.status_calls = []
        self.last_step_calls = []
        self.begin_calls = 0

    def begin_run(self, task_id, run_token, step=""):
        self.begin_calls += 1
        return True

    def update_last_step(self, task_id, step, run_token=None):
        self.last_step_calls.append({"step": step, "run_token": run_token})
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
         mock.patch.object(task_runner, "_get_nyxify_hold_reason", lambda profile_id, nyx_task=None: ""):
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

    def test_cdp_launch_timeout_exception_retries_whole_profile(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}
        attempts = []

        async def fake_run_profile_task(*args, **kwargs):
            attempts.append(args)
            if len(attempts) == 1:
                raise AdsPowerProfileNotOpenError(
                    "GUI control mode is selected, but profile k1abc could not "
                    "be opened through the AdsPower desktop app. (UI error: "
                    "Opened profile k1abc in the GUI but could not resolve its "
                    "CDP endpoint. Is the browser still launching?)"
                )
            return (True, "normal")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason",
                               lambda profile_id, nyx_task=None: ""), \
             mock.patch.object(task_runner, "NYX_BITMOJI_PROFILE_RETRIES", 1), \
             mock.patch.object(task_runner, "NYX_BITMOJI_RETRY_BACKOFF_SECONDS", 0):
            asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))

        self.assertEqual(len(attempts), 2)
        self.assertIn(
            "retrying_bitmoji_flow",
            [call["step"] for call in store.last_step_calls],
        )
        self.assertEqual(store.status_calls[-1]["status"], "DONE")

    def test_missing_profile_exception_is_not_retried(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1missing", "model": "willow"}
        attempts = []

        async def fake_run_profile_task(*args, **kwargs):
            attempts.append(args)
            raise AdsPowerProfileNotOpenError("profile does not exist: k1missing")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason",
                               lambda profile_id, nyx_task=None: ""), \
             mock.patch.object(task_runner, "NYX_BITMOJI_PROFILE_RETRIES", 2), \
             mock.patch.object(task_runner, "NYX_BITMOJI_RETRY_BACKOFF_SECONDS", 0):
            with self.assertRaises(AdsPowerProfileNotOpenError):
                asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))

        self.assertEqual(len(attempts), 1)

    def test_transient_bitmoji_exception_retries_whole_profile(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}
        attempts = []

        async def fake_run_profile_task(*args, **kwargs):
            attempts.append(args)
            if len(attempts) == 1:
                raise RuntimeError("Editor failed to load")
            return (True, "normal")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason",
                               lambda profile_id, nyx_task=None: ""), \
             mock.patch.object(task_runner, "NYX_BITMOJI_PROFILE_RETRIES", 1), \
             mock.patch.object(task_runner, "NYX_BITMOJI_RETRY_BACKOFF_SECONDS", 0):
            asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))

        self.assertEqual(len(attempts), 2)
        self.assertEqual(store.status_calls[-1]["status"], "DONE")

    def test_nyx_holds_profile_when_nyxify_has_not_reached_success(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}
        run_calls = []
        flush_calls = []

        async def fake_run_profile_task(*args, **kwargs):
            run_calls.append(args)
            return (True, "normal")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch("core.runner_flags.nyx_request_flush", lambda: flush_calls.append(1)), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason",
                               lambda profile_id, nyx_task=None: "waiting_for_nyxify_success"):
            asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))

        self.assertEqual(run_calls, [])
        self.assertEqual(store.begin_calls, 0)
        self.assertEqual(len(store.status_calls), 1)
        self.assertEqual(store.status_calls[0]["status"], "PENDING")
        self.assertEqual(store.status_calls[0]["step"], "waiting_for_nyxify_success")
        # A hold must re-arm the flush latch so the held row is retried on the
        # next poll even when the queue sits below the start threshold.
        self.assertEqual(flush_calls, [1])

    def test_nyx_fails_row_when_nyxify_signup_terminally_failed(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}
        run_calls = []

        async def fake_run_profile_task(*args, **kwargs):
            run_calls.append(args)
            return (True, "normal")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason",
                               lambda profile_id, nyx_task=None: "fail:nyxify_signup_failed"):
            asyncio.run(task_runner.process_queued_task(task, store, adspower=object(), logger=_FakeLogger()))

        self.assertEqual(run_calls, [])
        self.assertEqual(len(store.status_calls), 1)
        self.assertEqual(store.status_calls[0]["status"], "FAILED")
        self.assertEqual(store.status_calls[0]["step"], "nyxify_signup_failed")

    def _guard(self, nyxify_row, nyx_task=None, running_signups=False, continuous=True):
        fake_store = mock.Mock()
        fake_store.get_task_by_adspower_profile_id.return_value = nyxify_row
        fake_store.has_running_signups.return_value = running_signups

        with mock.patch.object(task_runner, "NyxifyTaskStore", return_value=fake_store), \
             mock.patch.object(task_runner, "load_nyxify_config",
                               return_value={"continuous_mode_enabled": continuous}):
            return task_runner._get_nyxify_hold_reason("k1abc", nyx_task)

    def test_guard_allows_profile_after_nyxify_queued_for_nyx(self):
        self.assertEqual(
            self._guard({"status": "DONE", "last_step": "queued_for_nyx"}), "")

    def test_guard_holds_matching_profile_before_nyxify_success(self):
        self.assertEqual(
            self._guard({"status": "RUNNING", "last_step": "running_signup"}),
            "waiting_for_nyxify_success")

    def test_guard_holds_during_fresh_close_bookkeeping(self):
        from datetime import datetime, timezone

        now_iso = datetime.now(timezone.utc).isoformat()
        self.assertEqual(
            self._guard({"status": "DONE", "last_step": "closing_profile", "updated_at": now_iso}),
            "waiting_for_nyxify_success")

    def test_guard_releases_stale_close_bookkeeping(self):
        self.assertEqual(
            self._guard({
                "status": "DONE",
                "last_step": "closing_profile",
                "updated_at": "2020-01-01T00:00:00+00:00",
            }),
            "")

    def test_guard_allows_bitmoji_after_post_signup_bookkeeping_failure(self):
        for step in ("profile_rename_failed", "nyx_handoff_failed", "profile_close_failed"):
            self.assertEqual(
                self._guard({"status": "FAILED", "last_step": step}), "", step)

    def test_guard_fails_row_for_pre_signup_failure(self):
        self.assertEqual(
            self._guard({"status": "FAILED", "last_step": "creating_adspower_profile"}),
            "fail:nyxify_signup_failed")

    def test_guard_holds_unmatched_young_row_only_while_signups_running(self):
        from datetime import datetime, timezone

        young = {"created_at": datetime.now(timezone.utc).isoformat()}
        self.assertEqual(
            self._guard(None, nyx_task=young, running_signups=True),
            "waiting_for_nyxify_profile_sync")
        # Queued-but-not-running signups cannot have created an unmatched
        # profile — the guard must not hold the whole Nyx queue for them.
        self.assertEqual(self._guard(None, nyx_task=young, running_signups=False), "")

    def test_guard_releases_unmatched_row_after_sync_window(self):
        old = {"created_at": "2020-01-01T00:00:00+00:00"}
        self.assertEqual(self._guard(None, nyx_task=old, running_signups=True), "")


if __name__ == "__main__":
    unittest.main()
