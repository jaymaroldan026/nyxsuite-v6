import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import nyx_handoff
from core.task_store import TaskStore


class NyxHandoffTests(unittest.TestCase):
    def test_api_handoff_queues_profile_and_requests_nyx_flush(self):
        calls = []

        def fake_api_json(path, payload=None, token="", **_kwargs):
            calls.append((path, payload or {}, token))
            if path == "/token":
                return {"token": "tok"}
            if path == "/queue/upsert":
                return {"ok": True, "count": 1}
            if path == "/bot/finish_remaining":
                return {"ok": True, "started": True}
            raise AssertionError(path)

        with mock.patch.object(nyx_handoff, "_api_json", side_effect=fake_api_json), \
                mock.patch.object(nyx_handoff, "_NYX_LOCAL_API_TOKEN", ""), \
                mock.patch.object(nyx_handoff, "_LOCAL_API_TOKEN_CACHED", False):
            result = nyx_handoff.enqueue_profile_for_nyx(
                "k1new",
                "Willow",
                logger=None,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "api")
        self.assertEqual(calls[1][0], "/queue/upsert")
        self.assertEqual(calls[1][1]["entries"], [{"profile_id": "k1new", "model": "Willow"}])
        self.assertEqual(calls[2][0], "/bot/finish_remaining")

    def test_direct_fallback_queues_profile_and_requests_flush(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nyx_tasks.db"
            calls = []

            def fake_api_json(*_args, **_kwargs):
                raise RuntimeError("api down")

            with mock.patch.object(nyx_handoff, "_api_json", side_effect=fake_api_json), \
                    mock.patch.object(nyx_handoff, "NYX_TASK_DB_PATH", db_path), \
                    mock.patch.object(nyx_handoff.runner_flags, "nyx_request_flush", side_effect=lambda: calls.append("flush")):
                result = nyx_handoff.enqueue_profile_for_nyx(
                    "k1fallback",
                    "Clea",
                    logger=None,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["method"], "direct")
            self.assertEqual(calls, ["flush"])

            rows = TaskStore(db_path=str(db_path)).list_tasks()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["profile_id"], "k1fallback")
            self.assertEqual(rows[0]["model"], "Clea")
            self.assertEqual(rows[0]["source"], "nyxify_continuous")


if __name__ == "__main__":
    unittest.main()
