"""Tests for AdsPower 'No local API permission' (code 9110) handling.

Covers the dedicated error class + detector, the failure classifier, the
preflight probe mapping, and the runner gate that keeps the queue PENDING
(instead of nuking it FAILED) while AdsPower rejects API calls.
"""

import unittest
from unittest import mock

import main
from core import runner_flags
from core.adspower import (
    AdsPowerManager,
    AdsPowerPermissionError,
    AdsPowerUnreachableError,
    _is_permission_error,
)


class PermissionDetectorTests(unittest.TestCase):
    def test_code_9110_is_permission(self):
        self.assertTrue(_is_permission_error({"code": 9110, "msg": "anything"}))

    def test_code_minus1_with_message(self):
        self.assertTrue(_is_permission_error({"code": -1, "msg": "No local API permission"}))

    def test_plain_string_message(self):
        self.assertTrue(_is_permission_error("No local API permission"))

    def test_benign_success_is_not_permission(self):
        self.assertFalse(_is_permission_error({"code": 0, "msg": "success"}))

    def test_unreachable_is_connection_error_subclass(self):
        self.assertTrue(issubclass(AdsPowerUnreachableError, ConnectionError))


class ClassifyTests(unittest.TestCase):
    def test_permission_9110_classifies(self):
        msg = "AdsPower API error: {'code': 9110, 'msg': 'No local API permission'}"
        self.assertEqual(main.classify_task_failure(msg), "adspower_permission")

    def test_permission_help_text_classifies(self):
        msg = "AdsPower Local API permission denied (code 9110). Open AdsPower -> Settings..."
        self.assertEqual(main.classify_task_failure(msg), "adspower_permission")

    def test_unreachable_classifies(self):
        self.assertEqual(
            main.classify_task_failure("AdsPower Local API is unreachable. Tried hosts: 127.0.0.1"),
            "adspower_unreachable",
        )

    def test_proxy_error_still_classifies(self):
        self.assertEqual(main.classify_task_failure("net::ERR_PROXY_CONNECTION_FAILED"), "proxy_error")

    def test_generic_error_unchanged(self):
        self.assertEqual(main.classify_task_failure("some unrelated failure"), "error")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


class PreflightTests(unittest.TestCase):
    """The auto-connect probe hits the keyless root /status endpoint (no API
    key, not rate-limited) — these mock the HTTP layer (session.get)."""

    def test_ok_when_status_code_zero(self):
        m = AdsPowerManager()
        m.session.get = mock.Mock(return_value=_FakeResponse({"code": 0, "msg": "success"}))
        r = m.preflight_check()
        self.assertTrue(r["ok"])
        self.assertEqual(r["code"], "ok")

    def test_permission_when_status_returns_9110(self):
        m = AdsPowerManager()
        m.session.get = mock.Mock(return_value=_FakeResponse({"code": 9110, "msg": "No local API permission"}))
        r = m.preflight_check()
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "adspower_permission")

    def test_unreachable_when_all_hosts_refuse(self):
        import requests
        m = AdsPowerManager()
        m.session.get = mock.Mock(side_effect=requests.exceptions.ConnectionError("refused"))
        r = m.preflight_check()
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "adspower_unreachable")


class _FakeAds:
    def __init__(self, result):
        self._result = result

    def reload_credentials(self):
        pass

    def preflight_check(self):
        return self._result


class GateTests(unittest.TestCase):
    def setUp(self):
        runner_flags.nyx_clear_health()
        main._adspower_health_state["code"] = None

    def tearDown(self):
        runner_flags.nyx_clear_health()
        main._adspower_health_state["code"] = None

    def test_gate_blocks_and_sets_health_flag(self):
        ads = _FakeAds({"ok": False, "code": "adspower_permission", "message": "denied"})
        self.assertFalse(main.adspower_preflight_gate(ads))
        health = runner_flags.nyx_get_health()
        self.assertIsNotNone(health)
        self.assertEqual(health.get("code"), "adspower_permission")

    def test_gate_allows_and_clears_health_flag(self):
        runner_flags.nyx_set_health({"code": "adspower_permission", "message": "old"})
        ads = _FakeAds({"ok": True, "code": "ok", "message": "reachable"})
        self.assertTrue(main.adspower_preflight_gate(ads))
        self.assertIsNone(runner_flags.nyx_get_health())


if __name__ == "__main__":
    unittest.main()
