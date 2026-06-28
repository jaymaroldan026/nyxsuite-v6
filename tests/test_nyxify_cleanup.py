import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nyxify_runner
from core.nyxify_cleanup import CLEANUP_DELETE_FAILED_STEP
from core.nyxify_task_store import NyxifyTaskStore


class FakeStore:
    def __init__(self):
        self.state = {
            "status": "FAILED",
            "last_step": "",
            "error": "",
            "adspower_id": "k1orphan",
            "adspower_profile_id": "k1orphan",
            "adspower_name": "Snapchat: test",
            "adspower_group": "Snapchat",
            "tags": ["Snapchat"],
        }
        self.updates = []
        self.proxy_updates = []

    def update_task_state(self, task_id, **kwargs):
        self.updates.append({"task_id": task_id, **kwargs})
        self.state.update(kwargs)

    def update_task_proxy(self, task_id, proxy_address):
        self.proxy_updates.append((task_id, proxy_address))


class FakeAdsPower:
    def __init__(self, delete_error=None):
        self.delete_error = delete_error
        self.closed = []
        self.deleted = []

    def close_profile(self, profile_id):
        self.closed.append(profile_id)
        return {"code": 0}

    def delete_profile(self, profile_id):
        self.deleted.append(profile_id)
        if self.delete_error:
            raise RuntimeError(self.delete_error)
        return {"code": 0}


async def async_true(*_args, **_kwargs):
    return True


async def unexpected_rotation(*_args, **_kwargs):
    raise AssertionError("Proxy rotation should not run when AdsPower delete failed.")


class NyxifyCleanupTests(unittest.TestCase):
    def test_failed_signup_cleanup_keeps_profile_id_when_delete_fails(self):
        store = FakeStore()
        adspower = FakeAdsPower(delete_error="AdsPower API error: {'code': -1, 'msg': 'user_ids is required'}")

        with mock.patch.object(nyxify_runner, "_request_snapboard_adspower_id_update", return_value=True), \
             mock.patch.object(nyxify_runner, "_wait_for_snapboard_update", async_true), \
             mock.patch.object(nyxify_runner, "_request_snapboard_rotation", unexpected_rotation):
            asyncio.run(
                nyxify_runner._cleanup_failed_created_profile(
                    1111,
                    {"row_key": "row-1"},
                    store,
                    adspower,
                    {"profile_id": "k1orphan", "name": "Snapchat: test"},
                    "unable_to_process",
                    "unable_to_process",
                )
            )

        self.assertEqual(store.state["status"], "FAILED")
        self.assertEqual(store.state["last_step"], CLEANUP_DELETE_FAILED_STEP)
        self.assertEqual(store.state["adspower_profile_id"], "k1orphan")
        self.assertEqual(store.state["adspower_id"], "k1orphan")
        self.assertIn("user_ids is required", store.state["error"])
        self.assertFalse(
            any(update.get("adspower_profile_id") == "" for update in store.updates),
            "local AdsPower profile id must not be cleared until delete succeeds",
        )

    def test_failed_signup_cleanup_clears_profile_fields_after_delete_success(self):
        store = FakeStore()
        adspower = FakeAdsPower()

        with mock.patch.object(nyxify_runner, "_request_snapboard_adspower_id_update", return_value=False):
            asyncio.run(
                nyxify_runner._cleanup_failed_created_profile(
                    1112,
                    {"row_key": "row-2"},
                    store,
                    adspower,
                    {"profile_id": "k1deleted", "name": "Snapchat: test"},
                    "unable_to_process",
                    "unable_to_process",
                )
            )

        self.assertEqual(store.state["adspower_profile_id"], "")
        self.assertEqual(store.state["adspower_id"], "")
        self.assertEqual(store.state["adspower_name"], "")
        self.assertEqual(store.state["adspower_group"], "")
        self.assertEqual(store.state["tags"], [])
        self.assertEqual(adspower.deleted, ["k1deleted"])

    def test_cleanup_requeues_pending_when_proxy_rotation_succeeds(self):
        store = FakeStore()
        adspower = FakeAdsPower()

        async def rotation_ok(*_args, **_kwargs):
            return "9.9.9.9:1:u:p"

        with mock.patch.object(nyxify_runner, "_request_snapboard_adspower_id_update", return_value=False), \
             mock.patch.object(nyxify_runner, "_request_snapboard_rotation", rotation_ok):
            asyncio.run(
                nyxify_runner._cleanup_failed_created_profile(
                    1113, {"row_key": "row-3"}, store, adspower,
                    {"profile_id": "k1del", "name": "Snapchat: test"},
                    "signup_automation_failed", "signup_automation_failed",
                )
            )

        self.assertEqual(store.state["status"], "PENDING")
        self.assertEqual(store.proxy_updates, [(1113, "9.9.9.9:1:u:p")])
        self.assertEqual(adspower.deleted, ["k1del"])

    def test_cleanup_requeues_pending_even_when_proxy_rotation_fails(self):
        # A failed SnapBoard rotation must NOT strand the row in RUNNING — the row
        # is requeued PENDING so the next cycle creates another (and rotates then).
        store = FakeStore()
        store.state["status"] = "RUNNING"
        adspower = FakeAdsPower()

        async def rotation_empty(*_args, **_kwargs):
            return ""

        with mock.patch.object(nyxify_runner, "_request_snapboard_adspower_id_update", return_value=False), \
             mock.patch.object(nyxify_runner, "_request_snapboard_rotation", rotation_empty):
            asyncio.run(
                nyxify_runner._cleanup_failed_created_profile(
                    1114, {"row_key": "row-4"}, store, adspower,
                    {"profile_id": "k1del2", "name": "Snapchat: test"},
                    "signup_automation_failed", "signup_automation_failed",
                )
            )

        self.assertEqual(store.state["status"], "PENDING")
        self.assertEqual(store.state["adspower_profile_id"], "")
        self.assertEqual(adspower.deleted, ["k1del2"])

    def test_cleanup_does_not_crash_without_row_key(self):
        # Latent UnboundLocalError guard: refreshed_proxy must be defined even when
        # row_key is empty (no proxy rotation path taken).
        store = FakeStore()
        adspower = FakeAdsPower()
        asyncio.run(
            nyxify_runner._cleanup_failed_created_profile(
                1115, {"row_key": ""}, store, adspower,
                {"profile_id": "k1norow", "name": "Snapchat: test"},
                "signup_automation_failed", "signup_automation_failed",
            )
        )
        self.assertEqual(store.state["status"], "PENDING")
        self.assertEqual(adspower.deleted, ["k1norow"])

    def test_cleanup_delete_failed_rows_are_selected_for_orphan_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = NyxifyTaskStore(db_path=Path(temp_dir) / "nyxify_tasks.db")
            task_id, _status = store.upsert_task(
                row_key="row-orphan",
                model="Snapchat",
                ip_address="1.2.3.4",
                username="realuser",
                adspower_id="k1old",
            )
            store.update_task_state(
                task_id,
                status="FAILED",
                last_step=CLEANUP_DELETE_FAILED_STEP,
                error="delete failed",
                adspower_profile_id="k1old",
            )

            rows = store.get_cleanup_delete_failed_tasks()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], task_id)
        self.assertEqual(rows[0]["adspower_profile_id"], "k1old")


if __name__ == "__main__":
    unittest.main()
