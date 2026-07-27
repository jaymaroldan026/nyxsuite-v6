"""Outfit selection must survive Bitmoji rotating an item id out of its catalog.

Configured outfit ids (e.g. footwear=969, bottom=788) periodically disappear
from Bitmoji's catalog; the exact-match scan then never finds them and the whole
profile used to fail ("scroll forever" in nyx_bot.log). _apply_outfit_piece now
prefers the configured item but, when it's genuinely gone, dresses the avatar
with ANOTHER item from the *same configured pool* (random per profile) so the
substitute is always operator-approved. Picking any random catalog item is an
opt-in last resort (NYX_OUTFIT_FALLBACK_CATALOG=1) used only when the whole pool
has rotated out.
"""
import asyncio
import inspect
import json
import shutil
import subprocess
import unittest
from unittest import mock

from core.bitmoji import outfit_flow
from core.bitmoji_config import build_selector
from core.bitmoji.outfit_flow import BitmojiOutfitMixin


class _StubOutfit(BitmojiOutfitMixin):
    """Simulates the live editor: opening a category always works, and an item
    click succeeds unless that exact selector is in ``missing`` (or everything
    fails when ``all_fail``)."""

    def __init__(self, missing_selectors=(), all_fail=False):
        self.logger = None
        self.missing = set(missing_selectors)
        self.all_fail = all_fail
        self.clicked_items = []
        self.catalog_fallback_calls = []

    async def wait_if_paused(self):
        return None

    async def safe_click(self, selector_key, profile_id=None, retries=None):
        if str(selector_key).startswith("categories."):
            return True  # opening the category always works
        if self.all_fail or selector_key in self.missing:
            raise Exception(f"item not found: {selector_key}")
        self.clicked_items.append(selector_key)
        return True

    async def get_editor_context(self):
        return object()

    async def reset_editor_panel_scroll(self, ctx):
        return None

    async def wait_for_category_items(self, ctx=None, timeout=None):
        return None

    async def _click_any_item_in_open_category(self, category_key, param, profile_id, blocked_ids=None):
        self.catalog_fallback_calls.append((category_key, param, tuple(blocked_ids or ())))
        return True


class _StubApplyOutfit(BitmojiOutfitMixin):
    def __init__(self, selected_selectors):
        self.logger = None
        self.selected_selectors = selected_selectors
        self.color_calls = []

    async def wait_if_paused(self):
        return None

    async def _apply_outfit_piece(self, category_key, item_selector, profile_id, **kwargs):
        return self.selected_selectors[category_key]

    async def enable_tuck_if_available(self):
        return None

    async def pick_configured_color_option(self, profile_id, model, features, outfit_seed="", preferred_color=None,
                                           selected_option_id=None):
        self.color_calls.append((features, selected_option_id))
        return True

    async def human_delay(self, *args, **kwargs):
        return None


class _EmergencyScopeOutfit(BitmojiOutfitMixin):
    def __init__(self):
        self.logger = None

    async def reset_editor_panel_scroll(self, ctx):
        return None

    async def scroll_editor_panel(self, ctx, direction="down", amount=None):
        return {"moved": False}


class _EmergencyScopeCtx:
    def __init__(self):
        self.active_clicks = 0
        self.inactive_clicks = 0

    async def evaluate(self, source, arg=None):
        # The first in-panel attempt deliberately misses so this test exercises
        # the emergency DOM path, where stale panels used to win by DOM order.
        if "dispatchEvent" not in source:
            return False

        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("Node.js is required for the emergency selector DOM regression")
        harness = f"""
const source = {json.dumps(source)};
const requirements = {json.dumps((arg or {}).get("requirements", {}))};
class Tile {{
  constructor(name) {{ this.name=name; this.clicks=0; this.img={{src:'https://preview.bitmoji.com/avatar/top?top=42'}}; }}
  getBoundingClientRect() {{ return {{width:50,height:50,bottom:50,right:50}}; }}
  querySelector(query) {{ return query==='img' ? this.img : null; }}
  scrollIntoView() {{}}
  dispatchEvent() {{ this.clicks += 1; }}
}}
class Panel {{
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{ return query.includes('mix-and-match-container') ? [active] : []; }}
}}
const inactive = new Tile('inactive');
const active = new Tile('active');
const activePanel = new Panel();
globalThis.document = {{
  baseURI: 'https://sdk.bitmoji.com/',
  querySelectorAll(query) {{
    if (query.includes('current-category')) return [activePanel];
    if (query.includes('mix-and-match-container')) return [inactive, active];
    return [];
  }},
}};
globalThis.window = globalThis;
globalThis.MouseEvent = class MouseEvent {{ constructor() {{}} }};
const clicked = eval(`(${{source}})`)({{requirements}});
console.log(JSON.stringify({{clicked, active:active.clicks, inactive:inactive.clicks}}));
"""
        result = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        observed = json.loads(result.stdout)
        self.active_clicks = observed["active"]
        self.inactive_clicks = observed["inactive"]
        return observed["clicked"]


class _AnyItemScopeOutfit(BitmojiOutfitMixin):
    def __init__(self, ctx):
        self.logger = None
        self._ctx = ctx

    async def safe_click(self, selector_key, profile_id=None, retries=None):
        return True

    async def get_editor_context(self):
        return self._ctx

    async def reset_editor_panel_scroll(self, ctx):
        return None

    async def wait_for_category_items(self, ctx=None, timeout=None):
        return True


class _AnyItemScopeCtx:
    def __init__(self):
        self.active_clicks = 0
        self.inactive_clicks = 0

    async def evaluate(self, source, arg=None):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("Node.js is required for the catalog fallback DOM regression")
        harness = f"""
const source = {json.dumps(source)};
const args = {json.dumps(arg or {})};
class Tile {{
  constructor(name) {{ this.name=name; this.clicks=0; this.img={{src:'https://preview.bitmoji.com/avatar/top?top=42'}}; }}
  getBoundingClientRect() {{ return {{width:50,height:50,bottom:50,right:50}}; }}
  querySelector(query) {{ return query==='img' ? this.img : null; }}
  scrollIntoView() {{}}
  click() {{ this.clicks += 1; }}
}}
class Panel {{
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{ return query.includes('mix-and-match-container') ? [active] : []; }}
}}
const inactive = new Tile('inactive');
const active = new Tile('active');
const activePanel = new Panel();
globalThis.document = {{
  querySelectorAll(query) {{
    if (query.includes('current-category')) return [activePanel];
    if (query.includes('mix-and-match-container')) return [inactive, active];
    return [];
  }},
}};
const clicked = eval(`(${{source}})`)(args);
console.log(JSON.stringify({{clicked, active:active.clicks, inactive:inactive.clicks}}));
"""
        result = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        observed = json.loads(result.stdout)
        self.active_clicks = observed["active"]
        self.inactive_clicks = observed["inactive"]
        return observed["clicked"]


class _ReadinessOutfit(BitmojiOutfitMixin):
    def __init__(self):
        self.logger = None

    async def wait_if_paused(self):
        return None


class _ReadinessAmbiguityCtx:
    def __init__(self):
        self.evaluate_calls = 0

    def locator(self, selector):
        return self

    async def count(self):
        # A stale panel has an item, but resolver-aware readiness must not use it.
        return 1

    async def evaluate(self, source, arg=None):
        self.evaluate_calls += 1
        return False


class _PanelScrollSourceCtx:
    """Capture the editor scripts so the regression can run them together in a
    stale/active DOM where the old global heuristic would move the stale panel."""

    def __init__(self):
        self.calls = []

    async def evaluate(self, source, arg=None):
        self.calls.append((source, arg))
        return {"found": True, "moved": True}


class OutfitFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Skip the 0.6s inter-retry sleeps.
        self._sleep = mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock())
        self._sleep.start()

    async def asyncTearDown(self):
        self._sleep.stop()

    async def test_pool_fallback_selects_another_pool_item(self):
        pool = ["top=chosen", "top=alt1", "top=alt2"]
        stub = _StubOutfit(missing_selectors={"top=chosen"})
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.tops", "top=chosen", "prof1",
                fallback_param="top", fallback_pool=pool,
            )
        self.assertIn(ok, {"top=alt1", "top=alt2"})
        # It clicked an alternate from the pool, never the missing chosen item.
        self.assertTrue(stub.clicked_items)
        self.assertNotIn("top=chosen", stub.clicked_items)
        self.assertTrue(all(sel in {"top=alt1", "top=alt2"} for sel in stub.clicked_items))
        self.assertEqual(ok, stub.clicked_items[0])
        # And it never resorted to the any-catalog net.
        self.assertEqual(stub.catalog_fallback_calls, [])

    async def test_pool_fallback_is_deterministic_per_profile(self):
        pool = ["x=chosen", "x=a", "x=b", "x=c", "x=d"]
        picks = set()
        for _ in range(3):
            stub = _StubOutfit(missing_selectors={"x=chosen"})
            with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
                await stub._apply_outfit_piece(
                    "categories.tops", "x=chosen", "profX",
                    fallback_param="x", fallback_pool=pool,
                )
            picks.add(stub.clicked_items[0])
        self.assertEqual(len(picks), 1, "same profile must pick the same fallback item on reruns")

    async def test_pool_fallback_skips_blocked_ids(self):
        # Every non-blocked alternate is missing except top=930; top=924 is blocked
        # and must never be clicked even though it is present in the catalog.
        pool = ["top=chosen", "top=924", "top=930"]
        stub = _StubOutfit(missing_selectors={"top=chosen"})
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.tops", "top=chosen", "prof1",
                fallback_param="top", blocked_ids={"924"}, fallback_pool=pool,
            )
        self.assertTrue(ok)
        self.assertEqual(stub.clicked_items, ["top=930"])

    async def test_no_fallback_without_pool(self):
        stub = _StubOutfit(missing_selectors={"top=chosen"})
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            with self.assertRaises(Exception):
                await stub._apply_outfit_piece("categories.tops", "top=chosen", "prof1", fallback_param="top")
        self.assertEqual(stub.catalog_fallback_calls, [])

    async def test_no_fallback_when_disabled(self):
        stub = _StubOutfit(missing_selectors={"bottom=chosen"})
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", False):
            with self.assertRaises(Exception):
                await stub._apply_outfit_piece(
                    "categories.bottoms", "bottom=chosen", "prof1",
                    fallback_param="bottom", fallback_pool=["bottom=chosen", "bottom=alt"],
                )
        self.assertEqual(stub.clicked_items, [])

    async def test_exact_item_preferred_no_fallback(self):
        stub = _StubOutfit(missing_selectors=set())
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.tops", "top=chosen", "prof1",
                fallback_param="top", fallback_pool=["top=chosen", "top=alt"],
            )
        self.assertEqual(ok, "top=chosen")
        self.assertEqual(stub.clicked_items, ["top=chosen"], "the exact item must be used when present")

    def test_outerwear_is_recognised_as_an_outfit_selector(self):
        self.assertTrue(_StubOutfit().is_outfit_selector(
            "xpath=//img[contains(@src,'/avatar/outerwear?outerwear=42')]",
        ))

    def test_live_outfit_selector_allows_bare_mix_and_match_tiles(self):
        source = inspect.getsource(BitmojiOutfitMixin.click_outfit_item)
        self.assertIn('.mix-and-match-container, [class*="mix-and-match-container"]', source)
        self.assertNotIn('.mix-and-match-container[tabindex="0"]', source)

    def test_live_outfit_selector_scopes_to_a_visible_non_scrollable_panel(self):
        source = inspect.getsource(BitmojiOutfitMixin.click_outfit_item)
        self.assertNotIn("isVisible(el) && isScrollable(el)", source)

    async def test_emergency_selector_never_clicks_an_exact_tile_in_a_stale_panel(self):
        ctx = _EmergencyScopeCtx()
        await _EmergencyScopeOutfit().click_outfit_item(ctx, build_selector("tops", "42"))

        self.assertGreater(ctx.active_clicks, 0)
        self.assertEqual(ctx.inactive_clicks, 0)

    async def test_catalog_fallback_never_clicks_an_eligible_tile_in_a_stale_panel(self):
        ctx = _AnyItemScopeCtx()
        clicked = await _AnyItemScopeOutfit(ctx)._click_any_item_in_open_category(
            "categories.tops", "top", "p1",
        )

        self.assertTrue(clicked)
        self.assertEqual(ctx.active_clicks, 1)
        self.assertEqual(ctx.inactive_clicks, 0)

    async def test_panel_reset_and_scroll_use_the_resolved_active_panel(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the panel scroll DOM regression")
        ctx = _PanelScrollSourceCtx()
        outfit = BitmojiOutfitMixin()

        await outfit.reset_editor_panel_scroll(ctx)
        await outfit.scroll_editor_panel(ctx, direction="down", amount=250)
        reset_source, reset_arg = ctx.calls[0]
        scroll_source, scroll_arg = ctx.calls[1]
        self.assertIsNone(reset_arg)
        self.assertEqual(scroll_arg, {"direction": "down", "amount": 250})

        harness = f"""
const resetSource = {json.dumps(reset_source)};
const scrollSource = {json.dumps(scroll_source)};
class Tile {{
  constructor(optionId, offsetTop) {{ this.optionId = optionId; this.offsetTop = offsetTop; }}
  getBoundingClientRect() {{ return {{width:50,height:50,bottom:50,right:50}}; }}
}}
class Panel {{
  constructor(name, top, tile) {{
    this.name = name;
    this.scrollTop = top;
    this.scrollHeight = 900;
    this.clientHeight = 100;
    this.tile = tile;
  }}
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{ return query.includes('mix-and-match-container') ? [this.tile] : []; }}
}}
const stale = new Panel('stale', 80, new Tile('stale', 250));
const exactActiveTile = new Tile('42', 250);
const active = new Panel('active', 90, exactActiveTile);
globalThis.document = {{
  querySelectorAll(query) {{
    if (query === '[data-nyx-active]') return [active];
    if (query.includes('current-category')) return [];
    if (query.includes('traits-container')) return [stale];
    if (query.includes('fashion-traits')) return [];
    if (query.includes('avatar-builder-category-container')) return [];
    if (query.includes('scrollable')) return [];
    return [];
  }},
}};
const reset = eval(`(${{resetSource}})`);
const scroll = eval(`(${{scrollSource}})`);
reset();
const result = scroll({json.dumps(scroll_arg)});
console.log(JSON.stringify({{
  result,
  activeTop: active.scrollTop,
  staleTop: stale.scrollTop,
  exactTileRevealed: active.scrollTop >= exactActiveTile.offsetTop,
}}));
"""
        result = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        observed = json.loads(result.stdout)

        self.assertTrue(observed["result"]["found"])
        self.assertTrue(observed["result"]["moved"])
        self.assertEqual(observed["activeTop"], 250)
        self.assertEqual(observed["staleTop"], 80)
        self.assertTrue(observed["exactTileRevealed"])

    def test_active_panel_resolver_rejects_ambiguous_generic_panels(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the active panel resolver DOM regression")
        resolver = json.dumps(outfit_flow._OUTFIT_ACTIVE_PANEL_RESOLVER)
        harness = f"""
const resolver = {resolver};
class Tile {{
  getBoundingClientRect() {{ return {{width:50,height:50,bottom:50,right:50}}; }}
}}
class Panel {{
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{ return query.includes('mix-and-match-container') ? [new Tile()] : []; }}
}}
const first = new Panel();
const second = new Panel();
globalThis.document = {{
  querySelectorAll(query) {{
    if (query.includes('traits-container')) return [first, second];
    return [];
  }},
}};
const resolved = eval(`(() => {{ ${{resolver}} return activePanel !== null; }})`)();
console.log(JSON.stringify({{resolved}}));
"""
        result = subprocess.run([node, "-e", harness], check=True, text=True, capture_output=True)
        self.assertFalse(json.loads(result.stdout)["resolved"])

    def test_active_panel_resolver_prioritises_the_explicit_active_marker(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the active panel resolver DOM regression")
        resolver = json.dumps(outfit_flow._OUTFIT_ACTIVE_PANEL_RESOLVER)
        harness = f"""
const resolver = {resolver};
class Panel {{
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
}}
const active = new Panel();
const current = new Panel();
globalThis.document = {{
  querySelectorAll(query) {{
    if (query==='[data-nyx-active]') return [active];
    if (query.includes('current-category')) return [current];
    return [];
  }},
}};
const resolved = eval(`(() => {{ ${{resolver}} return activePanel === active; }})`)();
console.log(JSON.stringify({{resolved}}));
"""
        result = subprocess.run([node, "-e", harness], check=True, text=True, capture_output=True)
        self.assertTrue(json.loads(result.stdout)["resolved"])

    async def test_readiness_rejects_stale_items_when_panel_resolution_is_ambiguous(self):
        ctx = _ReadinessAmbiguityCtx()
        ready = await _ReadinessOutfit().wait_for_category_items(ctx, timeout=0.001)

        self.assertFalse(ready)
        self.assertGreater(ctx.evaluate_calls, 0)

    def test_selected_selector_recovers_a_safely_quoted_option_id(self):
        option_id = "shirt'\""
        selector = build_selector("tops", option_id)
        self.assertEqual(
            _StubOutfit().outfit_option_id_from_selector(selector, "tops"),
            option_id,
        )

    async def test_apply_outfit_passes_pool_fallback_option_to_colour_selection(self):
        stub = _StubApplyOutfit({
            "categories.tops": build_selector("tops", "top-fallback"),
            "categories.bottoms": build_selector("bottoms", "bottom-selected"),
            "categories.footwear": build_selector("footwear", "shoe-selected"),
        })
        outfit = {
            "mode": "separates",
            "top": "top=requested",
            "bottom": "bottom=requested",
            "shoes": "footwear=requested",
        }
        with mock.patch.object(outfit_flow, "generate_outfit", return_value=outfit):
            await stub.apply_outfit("profile-1", "M", "seed")

        self.assertEqual(stub.color_calls, [
            (("tops", "outfits"), "top-fallback"),
            (("bottoms",), "bottom-selected"),
            (("footwear",), "shoe-selected"),
        ])

    async def test_catalog_net_used_when_pool_exhausted_and_enabled(self):
        # Whole pool retired; the opt-in catalog net dresses the avatar so the
        # profile still completes.
        stub = _StubOutfit(all_fail=True)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True), \
             mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_CATALOG_FALLBACK", True):
            ok = await stub._apply_outfit_piece(
                "categories.tops", "top=chosen", "prof1",
                fallback_param="top", fallback_pool=["top=chosen", "top=alt"],
            )
        self.assertTrue(ok)
        self.assertEqual(len(stub.catalog_fallback_calls), 1)

    async def test_catalog_net_off_by_default(self):
        # Same fully-retired pool, but the catalog net is disabled (default) -> the
        # step fails rather than picking a random catalog item.
        stub = _StubOutfit(all_fail=True)
        with mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_FALLBACK", True), \
             mock.patch.object(outfit_flow, "_OUTFIT_ALLOW_CATALOG_FALLBACK", False):
            with self.assertRaises(Exception):
                await stub._apply_outfit_piece(
                    "categories.tops", "top=chosen", "prof1",
                    fallback_param="top", fallback_pool=["top=chosen", "top=alt"],
                )
        self.assertEqual(stub.catalog_fallback_calls, [])


if __name__ == "__main__":
    unittest.main()
