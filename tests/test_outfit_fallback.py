"""Outfit selection must survive Bitmoji rotating an item id out of its catalog.

Configured outfit ids (e.g. footwear=969, bottom=788) periodically disappear
from Bitmoji's catalog; the exact-match scan then never finds them and the whole
profile used to fail ("scroll forever" in nyx_bot.log). _apply_outfit_piece now
prefers the configured item but, when it's genuinely gone, dresses the avatar
with any available item of the same category so the profile completes.
"""
import unittest
from unittest import mock

from core.bitmoji import outfit_flow
from core.bitmoji.outfit_flow import BitmojiOutfitMixin


class _StubOutfit(BitmojiOutfitMixin):
    def __init__(self, item_fails=True):
        self.logger = None
        self.item_fails = item_fails
        self.fallback_calls = []

    async def wait_if_paused(self):
        return None

    async def safe_click(self, selector_key, profile_id=None, retries=None):
        if str(selector_key).startswith("categories."):
            return True  # opening the category always works
        if self.item_fails:
            raise Exception(f"item not found: {selector_key}")
        return True

    async def get_editor_context(self):
        return object()

    async def reset_editor_panel_scroll(self, ctx):
        return None

    async def wait_for_category_items(self, ctx=None, timeout=None):
        return None

    async def _click_any_item_in_open_category(self, category_key, param, profile_id, blocked_ids=None):
        self.fallback_calls.append((category_key, param, tuple(blocked_ids or ())))
        return True


class OutfitFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Skip the 0.6s inter-retry sleeps.
        self._sleep = mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock())
        self._sleep.start()

    async def asyncTearDown(self):
        self._sleep.stop()

    async def test_fallback_used_when_exact_item_missing(self):
        stub = _StubOutfit(item_fails=True)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.footwear", "xpath=...footwear=969...", "prof1",
                fallback_param="footwear", blocked_ids={"712"},
            )
        self.assertTrue(ok)
        self.assertEqual(len(stub.fallback_calls), 1)
        self.assertEqual(stub.fallback_calls[0][0], "categories.footwear")
        self.assertEqual(stub.fallback_calls[0][1], "footwear")

    async def test_no_fallback_when_disabled(self):
        stub = _StubOutfit(item_fails=True)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", False):
            with self.assertRaises(Exception):
                await stub._apply_outfit_piece(
                    "categories.bottoms", "xpath=...bottom=788...", "prof1", fallback_param="bottom",
                )
        self.assertEqual(stub.fallback_calls, [])

    async def test_no_fallback_without_param(self):
        stub = _StubOutfit(item_fails=True)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            with self.assertRaises(Exception):
                await stub._apply_outfit_piece("categories.tops", "xpath=...top=801...", "prof1")
        self.assertEqual(stub.fallback_calls, [])

    async def test_exact_item_preferred_no_fallback(self):
        stub = _StubOutfit(item_fails=False)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.tops", "xpath=...top=801...", "prof1", fallback_param="top",
            )
        self.assertTrue(ok)
        self.assertEqual(stub.fallback_calls, [], "fallback must not run when the exact item is found")


if __name__ == "__main__":
    unittest.main()
