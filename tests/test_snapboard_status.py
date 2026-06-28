import json
import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.nyxify_local_api import NyxifyLocalApiServer, _StatusUpdateStore
from core.nyxify_task_store import NyxifyTaskStore


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StatusUpdateStoreTests(unittest.TestCase):
    def test_request_pop_result_roundtrip(self):
        store = _StatusUpdateStore()
        store.request("snapboard:42", "Banned")

        popped = store.pop_pending()
        self.assertEqual(popped, {"row_key": "snapboard:42", "status": "Banned"})
        # Already dispatched within the debounce window -> not handed out again.
        self.assertIsNone(store.pop_pending())

        store.store_result("snapboard:42", True)
        result = store.get_result("snapboard:42")
        self.assertTrue(result["success"])

    def test_failed_result_is_redispatched(self):
        store = _StatusUpdateStore()
        store.request("snapboard:7", "Banned")
        self.assertIsNotNone(store.pop_pending())

        store.store_result("snapboard:7", False, error="no select")
        # A failure clears the dispatched flag so the poller retries it.
        self.assertEqual(store.pop_pending(), {"row_key": "snapboard:7", "status": "Banned"})


class StatusUpdateApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "nyxify_tasks.db"
        self.store = NyxifyTaskStore(db_path=str(db_path))
        self.port = _free_port()
        self.server = NyxifyLocalApiServer(
            self.store, host="127.0.0.1", port=self.port, token="testtoken"
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
            headers={"Content-Type": "application/json", "X-Nyxify-Token": "testtoken"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path):
        req = urllib.request.Request(
            self.base + path, headers={"X-Nyxify-Token": "testtoken"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_status_update_request_pending_result_flow(self):
        # Bitmoji bot requests a Banned status for a SnapBoard row.
        resp = self._post("/status_update/request", {"row_key": "snapboard:99", "status": "Banned"})
        self.assertTrue(resp["ok"])

        # Content script polls and receives it.
        pending = self._get("/status_update/pending")
        self.assertEqual(pending["request"], {"row_key": "snapboard:99", "status": "Banned"})

        # Content script reports success; the bot confirms via /status.
        self._post("/status_update/result", {"row_key": "snapboard:99", "success": True})
        status = self._get("/status_update/status?row_key=snapboard:99")
        self.assertTrue(status["done"])
        self.assertTrue(status["success"])

    def test_status_update_requires_row_and_status(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/status_update/request", {"row_key": "snapboard:1"})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
