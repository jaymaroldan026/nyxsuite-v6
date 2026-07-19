"""Nyx auto sign-in credential resolution.

When a Bitmoji run opens a profile whose Snapchat session dropped (the sign-in
page shows instead of the OAuth consent), Nyx must sign back in using the
SnapBoard row's password — the password the account was created with — and the
username Nyxify confirmed on the welcome page, not a fixed default.
"""

import unittest
from unittest import mock

from core import task_runner


class _Logger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


def _resolve(row, env=None):
    fake_store = mock.Mock()
    fake_store.get_task_by_adspower_profile_id.return_value = row
    # Clear the env password vars unless the test explicitly sets them, so the
    # host environment can't change the resolved source.
    clean_env = {"SNAPCHAT_LOGIN_PASSWORD": "", "SNAPCHAT_DEFAULT_PASSWORD": ""}
    clean_env.update(env or {})
    with mock.patch.object(task_runner, "NyxifyTaskStore", return_value=fake_store), \
            mock.patch.dict("os.environ", clean_env, clear=False):
        return task_runner.resolve_snapchat_credentials("k1abc", _Logger())


class AutoLoginCredentialTests(unittest.TestCase):
    def test_uses_snapboard_password_and_username(self):
        creds = _resolve({"username": "cleesmirk", "password": "SnapBoardPw1!"})
        self.assertEqual(creds["source"], "snapboard.password")
        self.assertEqual(creds["username"], "cleesmirk")
        self.assertEqual(creds["password"], "SnapBoardPw1!")

    def test_blank_snapboard_password_falls_back_but_keeps_username(self):
        creds = _resolve({"username": "coolgirl", "password": ""})
        self.assertEqual(creds["source"], "default.password")
        self.assertEqual(creds["username"], "coolgirl")
        self.assertEqual(creds["password"], task_runner.DEFAULT_SNAPCHAT_PASSWORD)

    def test_no_nyxify_row_uses_default_and_blank_username(self):
        creds = _resolve(None)
        self.assertEqual(creds["source"], "default.password")
        self.assertEqual(creds["username"], "")
        self.assertEqual(creds["password"], task_runner.DEFAULT_SNAPCHAT_PASSWORD)

    def test_uses_nyx_queue_credentials_when_nyxify_row_is_missing(self):
        fake_nyxify_store = mock.Mock()
        fake_nyxify_store.get_task_by_adspower_profile_id.return_value = None
        fake_nyx_store = mock.Mock()
        fake_nyx_store.get_task_by_profile_id.return_value = {
            "profile_id": "k1abc",
            "username": "queueuser",
            "password": "QueuePw3!",
        }

        clean_env = {"SNAPCHAT_LOGIN_PASSWORD": "", "SNAPCHAT_DEFAULT_PASSWORD": ""}
        with mock.patch.object(task_runner, "NyxifyTaskStore", return_value=fake_nyxify_store), \
                mock.patch.object(task_runner, "TaskStore", return_value=fake_nyx_store), \
                mock.patch.dict("os.environ", clean_env, clear=False):
            creds = task_runner.resolve_snapchat_credentials("k1abc", _Logger())

        self.assertEqual(creds["source"], "nyx_queue.password")
        self.assertEqual(creds["username"], "queueuser")
        self.assertEqual(creds["password"], "QueuePw3!")

    def test_env_password_beats_default_when_snapboard_blank(self):
        creds = _resolve({"username": "u", "password": ""}, env={"SNAPCHAT_LOGIN_PASSWORD": "EnvPw2@"})
        self.assertEqual(creds["source"], "env.password")
        self.assertEqual(creds["password"], "EnvPw2@")

    def test_store_error_is_swallowed_and_falls_back(self):
        fake_store = mock.Mock()
        fake_store.get_task_by_adspower_profile_id.side_effect = RuntimeError("db locked")
        with mock.patch.object(task_runner, "NyxifyTaskStore", return_value=fake_store):
            creds = task_runner.resolve_snapchat_credentials("k1abc", _Logger())
        self.assertEqual(creds["username"], "")
        self.assertTrue(creds["password"])


if __name__ == "__main__":
    unittest.main()
