import unittest
import sys
import types
from unittest import mock

_playwright_pkg = types.ModuleType("playwright")
_playwright_async_api = types.ModuleType("playwright.async_api")
_playwright_async_api.async_playwright = lambda: None
_playwright_async_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _playwright_pkg)
sys.modules.setdefault("playwright.async_api", _playwright_async_api)
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))

from core.bitmoji_creator import BitmojiCreator


class _FakePage:
    def __init__(self, url="https://www.bitmoji.com/avatar/create/?require_snapchat"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, pages):
        self._pages = list(pages)

    @property
    def pages(self):
        return list(self._pages)


class _FakeBrowser:
    def __init__(self, contexts):
        self.contexts = list(contexts)


class _FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


class BitmojiCreatorCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def _run_delay_and_total_sleep(self, creator, delay_value):
        with mock.patch("random.uniform", side_effect=lambda low, _high: low), \
                mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as sleep_mock:
            await creator.human_delay(delay_value, delay_value, respect_jitter=False)

        return sum(call.args[0] for call in sleep_mock.await_args_list)

    def _creator_for_delay_tests(self):
        creator = BitmojiCreator.__new__(BitmojiCreator)
        creator.automation_speed = 0.1
        creator.refresh_runtime_settings = mock.Mock(return_value=False)
        creator.wait_if_paused = mock.AsyncMock()
        creator._automation_speed_active = False
        return creator

    async def test_human_delay_ignores_speed_outside_editor_scope(self):
        creator = self._creator_for_delay_tests()

        total_sleep = await self._run_delay_and_total_sleep(creator, 0.1)

        self.assertAlmostEqual(total_sleep, 0.1)

    async def test_human_delay_applies_speed_inside_editor_scope(self):
        creator = self._creator_for_delay_tests()

        async with creator.automation_speed_phase("editor"):
            total_sleep = await self._run_delay_and_total_sleep(creator, 0.1)

        self.assertAlmostEqual(total_sleep, 1.0)
        self.assertFalse(creator._automation_speed_active)

    async def test_stop_preserves_work_tab_by_default(self):
        creator = BitmojiCreator.__new__(BitmojiCreator)
        creator.page = _FakePage()
        creator.playwright = _FakePlaywright()

        await creator.stop()

        self.assertFalse(creator.page.closed)
        self.assertTrue(creator.playwright.stopped)

    async def test_stop_can_close_work_tab_when_explicit(self):
        creator = BitmojiCreator.__new__(BitmojiCreator)
        creator.page = _FakePage()
        creator.playwright = _FakePlaywright()

        await creator.stop(close_page=True)

        self.assertTrue(creator.page.closed)
        self.assertTrue(creator.playwright.stopped)

    async def test_close_all_tabs_except_adspower_start_removes_signup_and_bitmoji_tabs(self):
        start_page = _FakePage("https://start.adspower.net/?id=k1abc&host=127.0.0.1:20725")
        signup_page = _FakePage("https://accounts.snapchat.com/v2/signup")
        error_page = _FakePage("https://accounts.snapchat.com/accounts/v2/403")
        bitmoji_create_page = _FakePage("https://www.bitmoji.com/avatar/create/?require_snapchat")
        bitmoji_login_page = _FakePage("https://www.bitmoji.com/login/?code=abc")
        context = _FakeContext([start_page, signup_page, error_page])
        second_context = _FakeContext([bitmoji_create_page, bitmoji_login_page])

        creator = BitmojiCreator.__new__(BitmojiCreator)
        creator.context = context
        creator.browser = _FakeBrowser([context, second_context])
        creator.page = bitmoji_login_page
        creator.logger = None

        closed = await creator.close_all_tabs_except_adspower_start()

        self.assertEqual(closed, 4)
        self.assertFalse(start_page.closed)
        self.assertTrue(signup_page.closed)
        self.assertTrue(error_page.closed)
        self.assertTrue(bitmoji_create_page.closed)
        self.assertTrue(bitmoji_login_page.closed)
        self.assertIsNone(creator.page)


if __name__ == "__main__":
    unittest.main()
