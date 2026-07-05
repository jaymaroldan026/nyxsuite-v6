import unittest

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
