import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import core.bitmoji_config as bitmoji_config
from core.nyx_local_api import NyxLocalApiServer
from core.task_store import TaskStore


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NyxLocalApiCredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "nyx_tasks.db"
        self.store = TaskStore(db_path=str(self.db_path))
        self.port = _free_port()
        self.server = NyxLocalApiServer(
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
            headers={"Content-Type": "application/json", "X-Nyx-Token": "testtoken"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path):
        req = urllib.request.Request(
            self.base + path, headers={"X-Nyx-Token": "testtoken"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_error(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json", "X-Nyx-Token": "testtoken"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(req, timeout=5)
        error = raised.exception
        try:
            return error.code, json.loads(error.read().decode("utf-8"))
        finally:
            error.close()

    def test_queue_upsert_stores_credentials_privately(self):
        response = self._post("/queue/upsert", {
            "entries": [{
                "profile_id": "k1api",
                "model": "Willow",
                "username": "apiuser",
                "password": "ApiPw7!",
            }],
        })
        self.assertTrue(response["ok"])

        public_rows = self._get("/queue")["rows"]
        self.assertEqual(public_rows[0]["profile_id"], "k1api")
        self.assertEqual(public_rows[0]["username"], "apiuser")
        self.assertEqual(public_rows[0]["has_password"], 1)
        self.assertNotIn("password", public_rows[0])

        private_row = self.store.get_task_by_profile_id("k1api")
        self.assertEqual(private_row["username"], "apiuser")
        self.assertEqual(private_row["password"], "ApiPw7!")

    def test_bitmoji_models_rejects_malformed_models_without_saving(self):
        data_dir = Path(self.tmp.name) / "data"
        data_dir.mkdir()
        models_path = data_dir / "bitmoji_models.json"
        existing = {"M": {"tops": {"mode": "fixed", "id": "5"}}}
        models_path.write_text(json.dumps(existing), encoding="utf-8")
        with mock.patch.object(bitmoji_config, "DATA_DIR", data_dir), \
             mock.patch.object(bitmoji_config, "MODELS_PATH", models_path):
            status, response = self._post_error("/bitmoji/models", {"models": []})
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertEqual(json.loads(models_path.read_text(encoding="utf-8")), existing)

    def test_bitmoji_models_rejects_a_non_mapping_json_body_without_disconnecting(self):
        data_dir = Path(self.tmp.name) / "data"
        data_dir.mkdir()
        models_path = data_dir / "bitmoji_models.json"
        existing = {"M": {"tops": {"mode": "fixed", "id": "5"}}}
        models_path.write_text(json.dumps(existing), encoding="utf-8")
        with mock.patch.object(bitmoji_config, "DATA_DIR", data_dir), \
             mock.patch.object(bitmoji_config, "MODELS_PATH", models_path):
            status, response = self._post_error("/bitmoji/models", [1])
        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertEqual(json.loads(models_path.read_text(encoding="utf-8")), existing)


if __name__ == "__main__":
    unittest.main()
