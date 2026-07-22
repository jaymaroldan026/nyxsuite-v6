import json
import socket
import sys
import tempfile
import types
import unittest
import urllib.request
from collections import deque
from pathlib import Path

from core.nyx_local_api import NyxLocalApiServer
from core.task_store import TaskStore


class _RequestsResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {}

    def raise_for_status(self):
        return None


class _RequestsSession:
    def __init__(self):
        self.trust_env = False

    def get(self, *_args, **_kwargs):
        return _RequestsResponse()

    def post(self, *_args, **_kwargs):
        return _RequestsResponse()


_requests_stub = types.ModuleType("requests")
_requests_stub.Session = _RequestsSession
_requests_stub.get = lambda *_args, **_kwargs: _RequestsResponse()
_requests_stub.post = lambda *_args, **_kwargs: _RequestsResponse()
_requests_stub.exceptions = types.SimpleNamespace(
    ConnectionError=ConnectionError,
    Timeout=TimeoutError,
    RequestException=Exception,
)
sys.modules.setdefault("requests", _requests_stub)
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
_playwright_pkg = types.ModuleType("playwright")
_playwright_async_api = types.ModuleType("playwright.async_api")
_playwright_async_api.async_playwright = lambda: None
_playwright_async_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _playwright_pkg)
sys.modules.setdefault("playwright.async_api", _playwright_async_api)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NyxRunNowPriorityTests(unittest.TestCase):
    def test_continuous_priority_tasks_are_claimed_before_normal_pending_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            store.upsert_task(
                profile_id="k1normal",
                model="Willow",
                source="extension_popup",
            )
            store.upsert_task(
                profile_id="k1continuous",
                model="Clea",
                source="nyxify_continuous",
                priority=100,
            )

            rows = store.get_pending_tasks()

            self.assertEqual([row["profile_id"] for row in rows[:2]], ["k1continuous", "k1normal"])
            self.assertEqual(rows[0]["priority"], 100)
            self.assertTrue(store.has_active_continuous_handoff())

            store.update_status(rows[0]["id"], "DONE", "completed")

            self.assertFalse(store.has_active_continuous_handoff())

    def test_normal_resync_does_not_downgrade_active_continuous_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            store.upsert_task(
                profile_id="k1continuous",
                model="Clea",
                source="nyxify_continuous",
                username="finaluser",
                password="FinalPw1!",
                priority=100,
            )

            store.upsert_task(
                profile_id="k1continuous",
                model="Clea",
                source="extension_popup",
                username="seeduser",
                password="OldPw1!",
                priority=0,
            )

            row = store.get_task_by_profile_id("k1continuous")
            self.assertEqual(row["source"], "nyxify_continuous")
            self.assertEqual(row["priority"], 100)
            self.assertEqual(row["username"], "finaluser")
            self.assertEqual(row["password"], "FinalPw1!")
            self.assertTrue(store.has_active_continuous_handoff())

    def test_mid_batch_refresh_reorders_pending_queue_for_new_run_now_task(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            store.upsert_task(
                profile_id="k1normal1",
                model="Willow",
                source="extension_popup",
            )
            store.upsert_task(
                profile_id="k1normal2",
                model="Willow",
                source="extension_popup",
            )
            pending_queue = deque(store.get_pending_tasks())

            store.upsert_task(
                profile_id="k1continuous",
                model="Clea",
                source="nyxify_continuous",
                priority=100,
            )

            refreshed = main._refresh_pending_queue(pending_queue, store)

            self.assertEqual(
                [row["profile_id"] for row in refreshed],
                ["k1continuous", "k1normal1", "k1normal2"],
            )

    def test_continuous_handoff_borrows_slot_from_normal_need_login_wait(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            normal_id, _ = store.upsert_task(
                profile_id="k1normal",
                model="Willow",
                source="extension_popup",
            )
            store.begin_run(normal_id, "normal-run", step="opening_profile")
            store.update_last_step(normal_id, "need_login", run_token="normal-run")
            store.upsert_task(
                profile_id="k1continuous",
                model="Tessa",
                source="nyxify_continuous",
                priority=100,
            )

            pending_queue = deque(store.get_pending_tasks())

            self.assertEqual(
                main._effective_concurrency_limit_for_queue(
                    1, store, pending_queue, active_task_count=1
                ),
                2,
            )

    def test_continuous_handoff_does_not_borrow_slot_from_active_work(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            normal_id, _ = store.upsert_task(
                profile_id="k1normal",
                model="Willow",
                source="extension_popup",
            )
            store.begin_run(normal_id, "normal-run", step="opening_profile")
            store.update_last_step(normal_id, "running_bitmoji_flow", run_token="normal-run")
            store.upsert_task(
                profile_id="k1continuous",
                model="Tessa",
                source="nyxify_continuous",
                priority=100,
            )

            pending_queue = deque(store.get_pending_tasks())

            self.assertEqual(
                main._effective_concurrency_limit_for_queue(
                    1, store, pending_queue, active_task_count=1
                ),
                1,
            )

    def test_startup_requeues_orphaned_running_continuous_handoff(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            task_id, _ = store.upsert_task(
                profile_id="k1continuous",
                model="Chloe",
                source="nyxify_continuous",
                priority=100,
            )
            store.begin_run(task_id, "dead-run", step="running_bitmoji_flow")

            requeued = main._reset_orphaned_running_tasks_on_startup(store)

            row = store.get_task_by_profile_id("k1continuous")
            self.assertEqual(requeued, 1)
            self.assertEqual(row["status"], "PENDING")
            self.assertEqual(row["last_step"], "requeued_after_runner_restart")
            self.assertEqual(row["priority"], 100)
            self.assertEqual(row["source"], "nyxify_continuous")


class NyxRunNowApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "nyx_tasks.db"
        self.store = TaskStore(db_path=str(self.db_path))
        self.port = _free_port()
        self.finish_calls = []
        self.server = NyxLocalApiServer(
            self.store,
            host="127.0.0.1",
            port=self.port,
            token="testtoken",
            action_handlers={
                "finish_remaining": lambda payload: self.finish_calls.append(dict(payload or {})) or {
                    "ok": True,
                    "started": True,
                    "message": "Nyx will run now.",
                },
            },
        )
        self.server.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json", "X-Nyx-Token": "testtoken"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_run_now_upserts_continuous_priority_task_and_starts_nyx(self):
        response = self._post("/queue/run_now", {
            "profile_id": "k1api",
            "model": "Clea",
            "username": "apiuser",
            "password": "ApiPw7!",
        })

        self.assertTrue(response["ok"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["action"], "created")
        self.assertEqual(self.finish_calls, [{}])
        self.assertTrue(response["start_result"]["ok"])

        row = self.store.get_task_by_profile_id("k1api")
        self.assertEqual(row["source"], "nyxify_continuous")
        self.assertEqual(row["priority"], 100)
        self.assertEqual(row["status"], "PENDING")
        self.assertEqual(row["username"], "apiuser")
        self.assertEqual(row["password"], "ApiPw7!")


if __name__ == "__main__":
    unittest.main()
