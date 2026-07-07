"""Deleted AdsPower profiles must leave the Nyx queue and stay out of it.

A profile that Nyxify (or a Replace action) deleted can only ever fail with
profile_missing when Nyx tries to open it. These tests cover the store-level
purge/archive that removes such rows and blocks re-queueing, plus the Nyxify
cleanup hook and the runner's run-time profile_missing archiving.
"""

import tempfile
import os
import unittest
from unittest import mock

from core.task_store import TaskStore


class DeletedProfilePurgeTests(unittest.TestCase):
    def setUp(self):
        self.db_path = tempfile.mktemp(suffix=".db")
        self.store = TaskStore(db_path=self.db_path)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_purge_removes_queue_row_and_blocks_requeue(self):
        self.store.upsert_task(profile_id="k1del", model="Clea", ignore_done_override=False)
        self.assertEqual(len(self.store.get_pending_tasks()), 1)

        removed = self.store.purge_deleted_profile("k1del")
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.store.get_pending_tasks()), 0)

        # Extension re-sync must not re-queue a deleted profile.
        _tid, action = self.store.upsert_task(profile_id="k1del", model="Clea")
        self.assertEqual(action, "ignored_missing")

    def test_purge_of_unknown_profile_still_archives(self):
        removed = self.store.purge_deleted_profile("k1never")
        self.assertEqual(removed, 0)
        _tid, action = self.store.upsert_task(profile_id="k1never", model="Emily")
        self.assertEqual(action, "ignored_missing")

    def test_archive_missing_leaves_existing_row_but_blocks_resync(self):
        self.store.upsert_task(profile_id="k1keep", model="Emily", ignore_done_override=False)
        self.assertTrue(self.store.archive_missing_profile("k1keep"))
        # The existing row is untouched (a run-time miss keeps the FAILED row
        # visible); a fresh extension upsert is blocked.
        _tid, action = self.store.upsert_task(profile_id="k1keep", model="Emily")
        self.assertEqual(action, "ignored_missing")

    def test_empty_profile_id_is_ignored(self):
        self.assertEqual(self.store.purge_deleted_profile(""), 0)
        self.assertFalse(self.store.archive_missing_profile("  "))


class NyxifyCleanupPurgeHookTests(unittest.TestCase):
    def test_confirmed_delete_purges_nyx_queue(self):
        from core import nyxify_cleanup

        adspower = mock.Mock()
        adspower.close_profile.return_value = {"code": 0}
        adspower.delete_profile.return_value = {"code": 0}

        with mock.patch("core.nyx_handoff.purge_profile_from_nyx_queue") as purge:
            result = nyxify_cleanup.close_and_delete_profile(adspower, "k1gone", log=None)

        self.assertTrue(result["deleted"])
        purge.assert_called_once()
        self.assertEqual(purge.call_args.args[0], "k1gone")

    def test_failed_delete_does_not_purge(self):
        from core import nyxify_cleanup

        adspower = mock.Mock()
        adspower.close_profile.return_value = {"code": 0}
        adspower.delete_profile.return_value = {"code": 500, "msg": "nope"}

        with mock.patch("core.nyx_handoff.purge_profile_from_nyx_queue") as purge:
            result = nyxify_cleanup.close_and_delete_profile(adspower, "k1stay", log=None)

        self.assertFalse(result["deleted"])
        purge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
