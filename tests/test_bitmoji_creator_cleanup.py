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
    def __init__(self):
        self.closed = False

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


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


if __name__ == "__main__":
    unittest.main()
