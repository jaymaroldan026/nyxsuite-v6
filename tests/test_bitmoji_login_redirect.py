"""Tests for the Bitmoji OAuth-callback (LOGIN_REDIRECT) detection.

Regression cover for the stuck-on-login loop: the bitmoji.com/login callback
page must be classified as LOGIN_REDIRECT (reload / re-OAuth recovery), never as
LOGIN (Snapchat credential auto-login, which has no form to fill there).
"""

import asyncio
import types
import unittest

from core.bitmoji.interaction_flow import BitmojiInteractionMixin


class _Flow(BitmojiInteractionMixin):
    """Minimal harness exposing only what the URL-classification methods touch."""

    def __init__(self, urls=None):
        self._urls = list(urls or [])

    async def get_contexts(self):
        return [types.SimpleNamespace(url=u) for u in self._urls]


def _ctx(url):
    return types.SimpleNamespace(url=url)


class IsBitmojiLoginRedirectTests(unittest.TestCase):
    def setUp(self):
        self.flow = _Flow()

    def _check(self, url):
        return asyncio.run(self.flow.is_bitmoji_login_redirect_context(_ctx(url)))

    def test_bitmoji_login_callback_is_redirect(self):
        url = "https://www.bitmoji.com/login/?code=ABC&state=XYZ#session_id=1"
        self.assertTrue(self._check(url))

    def test_snapchat_credential_page_is_not_redirect(self):
        self.assertFalse(self._check("https://accounts.snapchat.com/accounts/v2/login"))

    def test_editor_page_is_not_redirect(self):
        self.assertFalse(self._check("https://www.bitmoji.com/avatar/create/?require_snapchat"))

    def test_blank_url(self):
        self.assertFalse(self._check(""))


class InferSessionStateTests(unittest.TestCase):
    def _infer(self, urls):
        return asyncio.run(_Flow(urls).infer_session_state_from_urls())

    def test_login_callback_infers_login_redirect(self):
        self.assertEqual(self._infer(["https://www.bitmoji.com/login/?code=ABC"]), "LOGIN_REDIRECT")

    def test_snapchat_login_infers_login(self):
        self.assertEqual(self._infer(["https://accounts.snapchat.com/accounts/v2/login"]), "LOGIN")

    def test_oauth_infers_continue(self):
        self.assertEqual(
            self._infer(["https://accounts.snapchat.com/accounts/oauth2/authorize?x=1"]),
            "CONTINUE",
        )

    def test_avatar_create_infers_gender(self):
        self.assertEqual(self._infer(["https://www.bitmoji.com/avatar/create/?require_snapchat"]), "GENDER")

    def test_home_infers_account_home(self):
        self.assertEqual(self._infer(["https://www.bitmoji.com/home/"]), "ACCOUNT_HOME")


if __name__ == "__main__":
    unittest.main()
