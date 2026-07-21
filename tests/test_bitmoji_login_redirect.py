"""Tests for the Bitmoji OAuth-callback (LOGIN_REDIRECT) detection.

Regression cover for the stuck-on-login loop: the bitmoji.com/login callback
page must be classified as LOGIN_REDIRECT (reload / re-OAuth recovery), never as
LOGIN (Snapchat credential auto-login, which has no form to fill there).
"""

import asyncio
import sys
import types
import unittest
from contextlib import asynccontextmanager

sys.modules.setdefault("playwright", types.SimpleNamespace())
sys.modules.setdefault(
    "playwright.async_api",
    types.SimpleNamespace(async_playwright=lambda: None, TimeoutError=TimeoutError),
)

from core.bitmoji_creator import BitmojiCreator
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


class _AutoLoginFlow(BitmojiInteractionMixin):
    LOGIN_WITH_SNAPCHAT_SELECTORS = []
    OAUTH_CONTINUE_SELECTORS = []

    def __init__(self, states):
        self._states = list(states)
        self.logger = None

    async def get_snapchat_login_context(self):
        return None

    async def check_session_state(self, fast=False):
        if self._states:
            return self._states.pop(0)
        return "UNKNOWN"

    async def recover_login_redirect(self, where=""):
        return "CONTINUE"

    async def human_delay(self, *a, **k):
        return None


class AutoLoginTransitionTests(unittest.TestCase):
    def test_auto_login_returns_oauth_state_when_login_page_advances_without_form(self):
        flow = _AutoLoginFlow(["LOGIN", "LOGIN", "CONTINUE"])

        result = asyncio.run(
            flow.try_auto_snapchat_login(
                "k1abc",
                credentials={
                    "username": "newuser",
                    "password": "CreatedPw1!",
                    "source": "snapboard.password",
                },
            )
        )

        self.assertEqual(result, "CONTINUE")


class _CountLocator:
    async def count(self):
        return 1


class _Page:
    def locator(self, selector):
        return _CountLocator()


class _RunFlow(BitmojiCreator):
    def __init__(self, auto_login_state):
        self.page = _Page()
        self.last_result = "normal"
        self._auto_login_state = auto_login_state
        self.manual_login_calls = 0

    def refresh_runtime_settings(self, force=False):
        return None

    @asynccontextmanager
    async def transition_phase_slot(self, name):
        yield

    async def start(self):
        return None

    async def stop(self):
        return None

    async def open_bitmoji_page(self):
        return "LOGIN"

    async def try_auto_snapchat_login(self, *a, **k):
        return self._auto_login_state

    async def wait_for_manual_login_resume(self, progress_callback=None):
        self.manual_login_calls += 1
        if callable(progress_callback):
            progress_callback("need_login")
        return "CONTINUE"

    async def handle_oauth_continue(self):
        return None

    async def wait_for_post_login_state(self, timeout_seconds=None):
        return "GENDER"

    async def select_gender(self):
        return None

    async def wait_for_editor(self):
        return None

    async def apply_face_model(self, model, profile_id):
        return True

    async def apply_outfit(self, profile_id, model="", outfit_seed=""):
        return None

    async def save_bitmoji(self):
        return None

    async def human_delay(self, *a, **k):
        return None


class RunLoginProgressTests(unittest.TestCase):
    def test_run_does_not_emit_need_login_when_auto_login_advances_to_oauth(self):
        flow = _RunFlow("CONTINUE")
        steps = []

        result = asyncio.run(
            flow.run(
                "k1abc",
                "Willow",
                snapchat_credentials={
                    "username": "newuser",
                    "password": "CreatedPw1!",
                    "source": "snapboard.password",
                },
                browser_ready=True,
                progress_callback=steps.append,
            )
        )

        self.assertTrue(result)
        self.assertEqual(flow.manual_login_calls, 0)
        self.assertNotIn("need_login", steps)
        self.assertIn("authorizing_bitmoji", steps)

    def test_run_emits_need_login_when_auto_login_cannot_continue(self):
        flow = _RunFlow(None)
        steps = []

        result = asyncio.run(
            flow.run(
                "k1abc",
                "Willow",
                snapchat_credentials={
                    "username": "newuser",
                    "password": "CreatedPw1!",
                    "source": "snapboard.password",
                },
                browser_ready=True,
                progress_callback=steps.append,
            )
        )

        self.assertTrue(result)
        self.assertEqual(flow.manual_login_calls, 1)
        self.assertIn("need_login", steps)


if __name__ == "__main__":
    unittest.main()
