import unittest

from core.adspower import AdsPowerManager


class AdsPowerDeleteTests(unittest.TestCase):
    def _manager_with_post(self, callback):
        manager = AdsPowerManager.__new__(AdsPowerManager)
        manager._post_json = callback
        # __new__ bypasses __init__; supply the attributes the no-API fallback
        # path reads. GUI fallback OFF so these API-only tests never touch the GUI.
        manager._cdp_fallback_profiles = set()
        manager.ui_fallback_enabled = False
        return manager

    def test_delete_profile_sends_v2_profile_id_payload_first(self):
        calls = []

        def fake_post(path, payload=None, timeout=30, **_params):
            calls.append((path, payload, timeout))
            return {"code": 0}

        manager = self._manager_with_post(fake_post)
        manager.delete_profile("k1abc")

        self.assertEqual(calls[0][0], "/api/v2/browser-profile/delete")
        self.assertEqual(calls[0][1], {"Profile_id": ["k1abc"]})

    def test_delete_profile_falls_back_to_v1_user_ids(self):
        calls = []

        def fake_post(path, payload=None, timeout=30, **_params):
            calls.append((path, payload))
            if len(calls) == 1:
                raise RuntimeError("v2 failed")
            return {"code": 0}

        manager = self._manager_with_post(fake_post)
        manager.delete_profile("k1abc")

        self.assertEqual(calls[1][0], "/user/delete")
        self.assertEqual(calls[1][1], {"user_ids": ["k1abc"]})

    def test_delete_profile_never_uses_invalid_singular_user_id_payload(self):
        calls = []

        def fake_post(path, payload=None, timeout=30, **_params):
            calls.append((path, payload))
            raise RuntimeError("delete failed")

        manager = self._manager_with_post(fake_post)
        with self.assertRaises(RuntimeError):
            manager.delete_profile("k1abc")

        self.assertEqual(len(calls), 2)
        self.assertFalse(any("user_id" in payload for _path, payload in calls))

    def test_delete_profile_combined_error_includes_all_attempts(self):
        def fake_post(path, payload=None, timeout=30, **_params):
            raise RuntimeError(f"failed at {path}")

        manager = self._manager_with_post(fake_post)

        with self.assertRaises(RuntimeError) as captured:
            manager.delete_profile("k1abc")

        message = str(captured.exception)
        self.assertIn("/api/v2/browser-profile/delete", message)
        self.assertIn("Profile_id", message)
        self.assertIn("/user/delete", message)
        self.assertIn("user_ids", message)

    def test_delete_profile_requires_code_zero(self):
        calls = []

        def fake_post(path, payload=None, timeout=30, **_params):
            calls.append((path, payload))
            return {"code": -1, "msg": "user_ids is required"}

        manager = self._manager_with_post(fake_post)

        with self.assertRaises(RuntimeError) as captured:
            manager.delete_profile("k1abc")

        self.assertEqual(len(calls), 2)
        self.assertIn("did not confirm success", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
