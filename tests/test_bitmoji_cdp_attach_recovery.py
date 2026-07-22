import asyncio
import sys
import types
import unittest
from unittest import mock

if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pw_async = types.ModuleType("playwright.async_api")
    _pw_async.async_playwright = lambda: None
    _pw_async.TimeoutError = TimeoutError
    sys.modules["playwright"] = _pw
    sys.modules["playwright.async_api"] = _pw_async

from core.bitmoji_creator import BitmojiCreator, CdpAttachTimeoutError


class _FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(str(message))


class _HangingChromium:
    async def connect_over_cdp(self, _endpoint):
        await asyncio.sleep(60)


class _FakePlaywright:
    def __init__(self):
        self.chromium = _HangingChromium()
        self.stopped = False

    async def stop(self):
        self.stopped = True


class CdpAttachRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_attach_timeout_raises_typed_error_fast(self):
        playwright = _FakePlaywright()
        logger = _FakeLogger()

        async def fake_start():
            return playwright

        with mock.patch(
            "core.bitmoji_creator.async_playwright",
            return_value=types.SimpleNamespace(start=fake_start),
        ), mock.patch.object(BitmojiCreator, "CDP_ATTACH_TIMEOUT_SECONDS", 0.01), \
             mock.patch.object(BitmojiCreator, "CDP_ATTACH_ATTEMPTS", 1):
            creator = BitmojiCreator("ws://127.0.0.1:58328/devtools/browser/test", logger)
            with self.assertRaises(CdpAttachTimeoutError) as raised:
                await creator.start()

        self.assertIn("Timed out connecting to AdsPower CDP", str(raised.exception))
        self.assertTrue(playwright.stopped)
        self.assertTrue(any("CDP connect retry 1/1" in line for line in logger.warnings))


if __name__ == "__main__":
    unittest.main()
