"""The Nyxify temporary profile name (e.g. "Snapchat: xoxoxo") must never be
mistaken for the real Snapchat username during auto sign-in username extraction.

A profile that was created but not yet renamed shows the temp name; using its
"xoxoxo" remainder as the login identifier would sign in as the wrong (or a
nonexistent) account. The extractor filters that placeholder out.
"""

import asyncio
import sys
import types
import unittest
from unittest import mock

# Stub playwright before importing the interaction flow (same pattern the other
# suites use so the import doesn't require the real dependency).
if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pw_async = types.ModuleType("playwright.async_api")
    _pw_async.async_playwright = lambda: None
    _pw_async.TimeoutError = TimeoutError
    sys.modules["playwright"] = _pw
    sys.modules["playwright.async_api"] = _pw_async

from core.bitmoji.interaction_flow import BitmojiInteractionMixin


class _FakePage:
    def __init__(self, dom_username="", title=""):
        self._dom_username = dom_username
        self._title = title
        self.url = "https://start.adspower.net/"

    def is_closed(self):
        return False

    async def evaluate(self, _script):
        return self._dom_username

    async def title(self):
        return self._title


class _Harness(BitmojiInteractionMixin):
    def __init__(self, page):
        self.page = page
        self.context = None
        self.logger = None


class UsernamePlaceholderTests(unittest.IsolatedAsyncioTestCase):
    async def _extract(self, page, temp_name):
        harness = _Harness(page)
        with mock.patch(
            "core.nyxify_runtime_config.load_nyxify_config",
            return_value={"temporary_profile_name": temp_name},
        ):
            return await harness.extract_snapchat_username_from_browser_context()

    async def test_placeholder_from_dom_is_ignored(self):
        page = _FakePage(dom_username="xoxoxo")
        result = await self._extract(page, "Snapchat: xoxoxo")
        self.assertEqual(result, "")

    async def test_placeholder_from_title_is_ignored(self):
        page = _FakePage(dom_username="", title="Snapchat: xoxoxo")
        result = await self._extract(page, "Snapchat: xoxoxo")
        self.assertEqual(result, "")

    async def test_real_username_still_extracted(self):
        page = _FakePage(dom_username="cleesmirk")
        result = await self._extract(page, "Snapchat: xoxoxo")
        self.assertEqual(result, "cleesmirk")

    async def test_no_temp_name_configured_returns_username(self):
        page = _FakePage(dom_username="realuser")
        result = await self._extract(page, "")
        self.assertEqual(result, "realuser")


if __name__ == "__main__":
    unittest.main()
