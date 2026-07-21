"""Banned proxies must persist.

Two reported bugs: banning a subnet from the Proxy Ranking table "didn't save
automatically", and the banned list "cleared on restart/update". Root cause: an
ordinary extension config push (e.g. flipping a toggle) carried a stale/empty
``blocked_proxies`` and the ``/config`` endpoint replaced the stored list with
it, wiping bans added elsewhere. The fix: ``/config`` only replaces the list when
the caller sets ``blocked_proxies_replace`` (a deliberate banned-list editor);
``/proxy_ranking/ban`` stays additive.
"""
import http.client
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.nyxify_runtime_config as rc
from core.nyxify_local_api import NyxifyLocalApiServer


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ProxyBanPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        # Point the config at a temp file so we never touch the real one.
        self._patchers = [
            mock.patch.object(rc, "DATA_DIR", tmp),
            mock.patch.object(rc, "CONFIG_PATH", tmp / "nyxify_config.json"),
            mock.patch("core.proxy_ranking_store.ProxyRankingStore", mock.Mock()),
        ]
        for p in self._patchers:
            p.start()

        self.port = _free_port()
        self.api = NyxifyLocalApiServer(store=mock.Mock(), host="127.0.0.1", port=self.port, token="")
        self.api.start()

    def tearDown(self):
        self.api.stop()
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    def _post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return data

    def _blocked(self):
        return rc.load_nyxify_config()["blocked_proxies"]

    def test_ranking_ban_appends_and_persists(self):
        res = self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        self.assertTrue(res["ok"])
        self.assertEqual(self._blocked(), ["9.9"])

    def test_incidental_config_push_does_not_wipe_bans(self):
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        # A toggle save pushes the full config with a stale/empty blocked list
        # and NO replace flag — the ban must survive.
        self._post("/config", {"proxy_blocker_enabled": True, "blocked_proxies": []})
        self.assertEqual(self._blocked(), ["9.9"])

    def test_deliberate_edit_replaces_with_flag(self):
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        # The banned-proxies textarea (deliberate edit) sets the replace flag.
        self._post("/config", {"blocked_proxies": ["9.9", "10.10"], "blocked_proxies_replace": True})
        self.assertEqual(self._blocked(), ["9.9", "10.10"])

    def test_flagged_clear_unbans(self):
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        self._post("/config", {"banned_proxies": [], "blocked_proxies_replace": True})
        self.assertEqual(self._blocked(), [])

    def test_ranking_ban_accepts_full_proxy_value(self):
        # The popup ban routes a full proxy string through the additive endpoint.
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        res = self._post("/proxy_ranking/ban", {"value": "1.2.3.4:8080:u:p"})
        self.assertTrue(res["ok"])
        self.assertEqual(self._blocked(), ["9.9", "1.2.3.4:8080:u:p"])

    def test_ranking_ban_enables_proxy_blocker(self):
        self._post("/config", {"proxy_blocker_enabled": False})
        res = self._post("/proxy_ranking/ban", {"subnet": "9.9"})

        self.assertTrue(res["ok"])
        config = rc.load_nyxify_config()
        self.assertEqual(config["blocked_proxies"], ["9.9"])
        self.assertTrue(config["proxy_blocker_enabled"])

    def test_ban_is_idempotent(self):
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        self._post("/proxy_ranking/ban", {"subnet": "9.9"})
        self.assertEqual(self._blocked(), ["9.9"])

    def test_bulk_ranking_ban_appends_multiple_subnets_idempotently(self):
        res = self._post("/proxy_ranking/ban_many", {"subnets": ["9.9", "10.10", "9.9", ""]})
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(self._blocked(), ["9.9", "10.10"])

    def test_bulk_ranking_ban_enables_proxy_blocker(self):
        self._post("/config", {"proxy_blocker_enabled": False})
        res = self._post("/proxy_ranking/ban_many", {"subnets": ["9.9"]})

        self.assertTrue(res["ok"])
        config = rc.load_nyxify_config()
        self.assertEqual(config["blocked_proxies"], ["9.9"])
        self.assertTrue(config["proxy_blocker_enabled"])


if __name__ == "__main__":
    unittest.main()
