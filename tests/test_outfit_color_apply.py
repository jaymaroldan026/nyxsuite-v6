"""End-to-end outfit colour apply (``pick_configured_color_option``).

The operator's per-model colour choice (fixed, or random-from-pool) must now be
applied to the created avatar by clicking the matching swatch in the live colour
wheel — while staying fully backward compatible: when nothing is configured, or
the swatch can't be matched, it falls back to the existing random colour pick and
never raises (colour is cosmetic and must not fail a profile).
"""
import unittest
import asyncio
import json
import shutil
import subprocess
from unittest import mock

from core.bitmoji import outfit_flow
from core.bitmoji.outfit_flow import BitmojiOutfitMixin


class _FakeLocator:
    def __init__(self, ok=True):
        self._ok = ok

    @property
    def first(self):
        return self

    async def wait_for(self, state=None, timeout=None):
        if not self._ok:
            raise Exception("picker not visible")
        return None


class _FakeCtx:
    def __init__(self, clicked=True, picker_visible=True):
        self._clicked = clicked
        self._picker_visible = picker_visible
        self.evaluated = []

    def locator(self, selector):
        return _FakeLocator(self._picker_visible)

    async def evaluate(self, js, arg=None):
        if arg is not None:
            self.evaluated.append(arg)
        if arg is None and "colour-picker-container" in js:
            return self._picker_visible
        return self._clicked


class _PanelScopedPickerCtx:
    """Capture panel-local picker scripts for a stale-picker DOM regression."""

    def __init__(self):
        self.calls = []

    def locator(self, selector):
        return _FakeLocator()

    async def evaluate(self, source, arg=None):
        self.calls.append((source, arg))
        return True


class _StaleOnlyPickerCtx:
    """Record the panel-local fallback scripts without allowing DOM clicks."""

    def __init__(self):
        self.calls = []

    async def evaluate(self, source, arg=None):
        self.calls.append((source, arg))
        return False


class _AbsentPanelPickerCtx:
    def __init__(self):
        self.calls = []

    async def evaluate(self, source, arg=None):
        self.calls.append((source, arg))
        return False


class _Clock:
    def __init__(self, *values):
        self._values = iter(values)

    def time(self):
        return next(self._values)


class _StubColor(BitmojiOutfitMixin):
    def __init__(self, ctx):
        self.logger = None
        self._ctx = ctx
        self.context_calls = 0
        self.random_called = False
        self.random_args = None

    async def wait_if_paused(self):
        return None

    async def get_editor_context(self):
        self.context_calls += 1
        return self._ctx

    async def human_delay(self, *a, **k):
        return None

    async def pick_random_color_option(self, profile_id, outfit_seed="", preferred_color=None,
                                       active_panel_only=False, ctx=None):
        self.random_called = True
        self.random_args = (profile_id, outfit_seed, preferred_color)
        self.random_scope = (active_panel_only, ctx)
        return "RANDOM"


class _ScopedFallbackColor(BitmojiOutfitMixin):
    def __init__(self, ctx):
        self.logger = None
        self._ctx = ctx

    async def wait_if_paused(self):
        return None

    async def get_editor_context(self):
        return self._ctx

    async def human_delay(self, *args, **kwargs):
        return None


class PickConfiguredColorTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_color_clicks_swatch(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"):
            result = await stub.pick_configured_color_option("p1", "M", ("tops",))
        self.assertTrue(result)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, ["#ec2020"])

    async def test_swatch_not_matched_falls_back_to_random(self):
        ctx = _FakeCtx(clicked=False)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"):
            result = await stub.pick_configured_color_option("p1", "M", ("tops",), "seed", preferred_color={"x": 1})
        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.random_scope, (True, ctx))
        # preferred_color/seed forwarded to the fallback so legacy behaviour is intact
        self.assertEqual(stub.random_args, ("p1", "seed", {"x": 1}))

    async def test_absent_panel_local_picker_falls_back_to_random(self):
        ctx = _AbsentPanelPickerCtx()
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"), \
             mock.patch.object(outfit_flow.asyncio, "get_event_loop", return_value=_Clock(0, 0, 11)), \
             mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock()):
            result = await stub.pick_configured_color_option("p1", "M", "tops")

        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.random_scope, (True, ctx))
        self.assertEqual(len(ctx.calls), 1)
        self.assertIsNone(ctx.calls[0][1])

        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the panel-local picker DOM regression")
        ready_source = ctx.calls[0][0]
        harness = f"""
const readySource = {json.dumps(ready_source)};
class Option {{
  getBoundingClientRect() {{ return {{width:20,height:20,bottom:20,right:20}}; }}
}}
class Picker {{
  getBoundingClientRect() {{ return {{width:100,height:40,bottom:40,right:100}}; }}
  querySelectorAll(query) {{ return query.includes('colour-picker-option') ? [new Option()] : []; }}
}}
class Panel {{
  constructor(picker) {{ this.picker = picker; }}
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{
    if (query.includes('colour-picker-container') || query.includes('.colour-picker')) return this.picker ? [this.picker] : [];
    return [];
  }}
}}
const stalePanel = new Panel(new Picker());
const activePanel = new Panel(null);
globalThis.document = {{
  querySelectorAll(query) {{
    if (query === '[data-nyx-active]') return [activePanel];
    if (query.includes('current-category')) return [];
    if (query.includes('traits-container')) return [stalePanel];
    return [];
  }},
}};
console.log(JSON.stringify({{ready: eval(`(${{readySource}})`)()}}));
"""
        completed = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        self.assertFalse(json.loads(completed.stdout)["ready"])

    async def test_active_panel_random_colour_honours_preferred_hex(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the preferred hex colour picker regression")

        class PreferredHexCtx:
            def __init__(self):
                self.observed = None

            async def evaluate(self, source, arg=None):
                harness = f"""
const source = {json.dumps(source)};
const arg = {json.dumps(arg or {})};
class Option {{
  constructor(name, color) {{ this.name = name; this.color = color; this.clicks = 0; }}
  getBoundingClientRect() {{ return {{width:20,height:20,bottom:20,right:20}}; }}
  scrollIntoView() {{}}
  click() {{ this.clicks += 1; }}
}}
class Picker {{
  constructor(options) {{ this.options = options; }}
  getBoundingClientRect() {{ return {{width:100,height:40,bottom:40,right:100}}; }}
  querySelectorAll(query) {{ return query.includes('colour-picker-option') ? this.options : []; }}
}}
class Panel {{
  constructor(picker) {{ this.picker = picker; }}
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{
    if (query.includes('colour-picker-container') || query.includes('.colour-picker')) return [this.picker];
    return [];
  }}
}}
const blue = new Option('blue', 'rgb(48, 115, 183)');
const pink = new Option('pink', 'rgb(255, 154, 173)');
const activePanel = new Panel(new Picker([blue, pink]));
globalThis.document = {{
  querySelectorAll(query) {{
    if (query === '[data-nyx-active]') return [activePanel];
    return [];
  }},
}};
globalThis.getComputedStyle = (element) => ({{backgroundColor: element.color || '', background: element.color || ''}});
const clicked = eval(`(${{source}})`)(arg);
console.log(JSON.stringify({{clicked, blue: blue.clicks, pink: pink.clicks}}));
"""
                completed = await asyncio.to_thread(
                    subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
                )
                self.observed = json.loads(completed.stdout)
                return self.observed["clicked"]

        ctx = PreferredHexCtx()
        stub = _StubColor(ctx)
        result = await stub._pick_random_color_option_from_active_panel(
            "p1", "seed", preferred_color={"hex": "#ff9aad"}, ctx=ctx,
        )

        self.assertTrue(result)
        self.assertEqual(ctx.observed, {"clicked": True, "blue": 0, "pink": 1})

    async def test_verified_configured_colour_does_not_fallback_when_active_picker_is_absent(self):
        ctx = _AbsentPanelPickerCtx()
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {
            "M": {"tops": {"mode": "fixed", "id": "selected-top", "color": "#ec2020"}},
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models), \
             mock.patch.object(outfit_flow.asyncio, "get_event_loop", return_value=_Clock(0, 0, 11)), \
             mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock()):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertFalse(result)
        self.assertFalse(stub.random_called)
        self.assertEqual(len(ctx.calls), 1)
        self.assertIsNone(ctx.calls[0][1])

    async def test_verified_configured_colour_does_not_fallback_when_swatch_misses(self):
        ctx = _FakeCtx(clicked=False)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {
            "M": {"tops": {"mode": "fixed", "id": "selected-top", "color": "#ec2020"}},
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertFalse(result)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, ["#ec2020"])

    async def test_unverified_configured_colour_keeps_scoped_random_fallback_when_picker_is_absent(self):
        ctx = _AbsentPanelPickerCtx()
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors": []}],
                },
            },
        }
        models = {
            "M": {"tops": {"mode": "fixed", "id": "selected-top", "color": "#ec2020"}},
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models), \
             mock.patch.object(outfit_flow.asyncio, "get_event_loop", return_value=_Clock(0, 0, 11)), \
             mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock()):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.random_scope, (True, ctx))

    async def test_stale_picker_cannot_receive_the_configured_swatch(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the panel-local picker DOM regression")
        ctx = _PanelScopedPickerCtx()
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"):
            result = await stub.pick_configured_color_option("p1", "M", "tops")

        self.assertTrue(result)
        self.assertEqual(len(ctx.calls), 2, "must wait for the panel-local picker before clicking")
        ready_source, ready_arg = ctx.calls[0]
        click_source, click_arg = ctx.calls[1]
        self.assertIsNone(ready_arg)
        self.assertEqual(click_arg, "#ec2020")
        harness = f"""
const readySource = {json.dumps(ready_source)};
const clickSource = {json.dumps(click_source)};
class Option {{
  constructor(name, color) {{ this.name = name; this.color = color; this.clicks = 0; }}
  getBoundingClientRect() {{ return {{width:20,height:20,bottom:20,right:20}}; }}
  scrollIntoView() {{}}
  click() {{ this.clicks += 1; }}
}}
class Picker {{
  constructor(option) {{ this.option = option; }}
  getBoundingClientRect() {{ return {{width:100,height:40,bottom:40,right:100}}; }}
  querySelectorAll(query) {{ return query.includes('colour-picker-option') ? [this.option] : []; }}
}}
class Panel {{
  constructor(picker) {{ this.picker = picker; }}
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{
    if (query.includes('colour-picker-container') || query.includes('.colour-picker')) return [this.picker];
    return [];
  }}
}}
const staleOption = new Option('stale', 'rgb(236, 32, 32)');
const activeOption = new Option('active', 'rgb(236, 32, 32)');
const stalePanel = new Panel(new Picker(staleOption));
const activePanel = new Panel(new Picker(activeOption));
globalThis.document = {{
  querySelectorAll(query) {{
    if (query === '[data-nyx-active]') return [activePanel];
    if (query.includes('current-category')) return [];
    if (query === '.colour-picker-option') return [staleOption, activeOption];
    if (query.includes('traits-container')) return [stalePanel];
    return [];
  }},
}};
globalThis.getComputedStyle = (element) => ({{backgroundColor: element.color || ''}});
const ready = eval(`(${{readySource}})`)();
const clicked = eval(`(${{clickSource}})`)({json.dumps(click_arg)});
console.log(JSON.stringify({{ready, clicked, stale: staleOption.clicks, active: activeOption.clicks}}));
"""
        completed = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        observed = json.loads(completed.stdout)

        self.assertTrue(observed["ready"])
        self.assertTrue(observed["clicked"])
        self.assertEqual(observed["stale"], 0)
        self.assertEqual(observed["active"], 1)

    async def test_missing_active_picker_fallback_cannot_click_a_stale_picker(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the panel-local picker DOM regression")
        ctx = _StaleOnlyPickerCtx()
        stub = _ScopedFallbackColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"), \
             mock.patch.object(outfit_flow.asyncio, "get_event_loop", return_value=_Clock(0, 0, 11)), \
             mock.patch.object(outfit_flow.asyncio, "sleep", new=mock.AsyncMock()):
            result = await stub.pick_configured_color_option("p1", "M", "tops")

        self.assertFalse(result)
        self.assertEqual(len(ctx.calls), 2, "fallback must use the active-panel random path")
        ready_source, ready_arg = ctx.calls[0]
        fallback_source, fallback_arg = ctx.calls[1]
        self.assertIsNone(ready_arg)
        self.assertIsInstance(fallback_arg, dict)
        harness = f"""
const readySource = {json.dumps(ready_source)};
const fallbackSource = {json.dumps(fallback_source)};
const fallbackArgs = {json.dumps(fallback_arg)};
class Option {{
  constructor() {{ this.clicks = 0; }}
  getBoundingClientRect() {{ return {{width:20,height:20,bottom:20,right:20}}; }}
  scrollIntoView() {{}}
  click() {{ this.clicks += 1; }}
}}
class Picker {{
  constructor(option) {{ this.option = option; }}
  getBoundingClientRect() {{ return {{width:100,height:40,bottom:40,right:100}}; }}
  querySelectorAll(query) {{ return query.includes('colour-picker-option') ? [this.option] : []; }}
}}
class Panel {{
  constructor(picker) {{ this.picker = picker; }}
  getBoundingClientRect() {{ return {{width:300,height:300,bottom:300,right:300}}; }}
  querySelectorAll(query) {{
    if (query.includes('colour-picker-container') || query.includes('.colour-picker')) return this.picker ? [this.picker] : [];
    return [];
  }}
}}
const staleOption = new Option();
const stalePanel = new Panel(new Picker(staleOption));
const activePanel = new Panel(null);
globalThis.document = {{
  querySelectorAll(query) {{
    if (query === '[data-nyx-active]') return [activePanel];
    if (query.includes('current-category')) return [];
    if (query.includes('traits-container')) return [stalePanel];
    if (query === '.colour-picker-option') return [staleOption];
    return [];
  }},
}};
globalThis.getComputedStyle = () => ({{background: '', backgroundColor: ''}});
const ready = eval(`(${{readySource}})`)();
const fallback = eval(`(${{fallbackSource}})`)(fallbackArgs);
console.log(JSON.stringify({{ready, fallback, stale: staleOption.clicks}}));
"""
        completed = await asyncio.to_thread(
            subprocess.run, [node, "-e", harness], check=True, text=True, capture_output=True,
        )
        observed = json.loads(completed.stdout)

        self.assertFalse(observed["ready"])
        self.assertFalse(observed["fallback"])
        self.assertEqual(observed["stale"], 0)

    async def test_no_config_uses_random_without_touching_picker(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value=None):
            result = await stub.pick_configured_color_option("p1", "M", ("tops", "outfits"))
        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.random_scope, (False, None))
        self.assertEqual(ctx.evaluated, [])  # never opened the colour wheel

    async def test_preset_preferred_hex_uses_active_panel_when_no_model_colour_exists(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        preferred = {"hex": "#ff9aad"}
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value=None):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", "seed", preferred_color=preferred,
            )

        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.random_scope, (True, None))
        self.assertEqual(stub.random_args, ("p1", "seed", preferred))
        self.assertEqual(ctx.evaluated, [])

    async def test_string_feature_is_accepted(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#010203"):
            result = await stub.pick_configured_color_option("p1", "M", "footwear")
        self.assertTrue(result)
        self.assertEqual(ctx.evaluated, ["#010203"])

    async def test_tries_each_feature_until_a_colour_resolves(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)

        def resolve(model, feature, models):
            return "#123456" if feature == "outfits" else None

        with mock.patch("core.bitmoji_config.load_models", return_value={}), \
             mock.patch("core.bitmoji_config.resolve_option_color", side_effect=resolve):
            result = await stub.pick_configured_color_option("p1", "M", ("tops", "outfits"))
        self.assertTrue(result)
        self.assertEqual(ctx.evaluated, ["#123456"])

    async def test_verified_colorless_item_skips_color_lookup_and_picker(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "colorless-top", "colors_verified": True, "colors": []}],
                },
            },
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.resolve_option_color") as resolve:
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="colorless-top",
            )

        self.assertFalse(result)
        resolve.assert_not_called()
        self.assertEqual(stub.context_calls, 0)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, [])

    async def test_verified_colorless_second_feature_skips_colour_lookup_and_picker(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "shared-item", "colors_verified": True, "colors": ["#ec2020"]}],
                },
                "outfits": {
                    "options": [{"id": "shared-item", "colors_verified": True, "colors": []}],
                },
            },
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.resolve_option_color") as resolve:
            result = await stub.pick_configured_color_option(
                "p1", "M", ("tops", "outfits"), selected_option_id="shared-item",
            )

        self.assertFalse(result)
        resolve.assert_not_called()
        self.assertEqual(stub.context_calls, 0)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, [])

    async def test_invalid_fixed_configured_colour_leaves_verified_item_unchanged(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {
            "M": {"tops": {"mode": "fixed", "id": "selected-top", "color": "#010203"}},
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertFalse(result)
        self.assertEqual(stub.context_calls, 0)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, [])

    async def test_invalid_random_configured_colour_leaves_verified_item_unchanged(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {
            "M": {"tops": {"mode": "random", "pool": ["selected-top"], "colors": ["#010203"]}},
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertFalse(result)
        self.assertEqual(stub.context_calls, 0)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, [])

    async def test_fixed_item_without_a_configured_colour_keeps_legacy_random_fallback(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {"M": {"tops": {"mode": "fixed", "id": "selected-top"}}}
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.context_calls, 0)
        self.assertEqual(ctx.evaluated, [])

    async def test_random_item_without_a_configured_colour_pool_keeps_legacy_random_fallback(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        models = {"M": {"tops": {"mode": "random", "pool": ["selected-top"]}}}
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value=models):
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertEqual(result, "RANDOM")
        self.assertTrue(stub.random_called)
        self.assertEqual(stub.context_calls, 0)
        self.assertEqual(ctx.evaluated, [])

    async def test_selected_item_id_constrains_colour_resolution(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        catalog = {
            "features": {
                "tops": {
                    "options": [{"id": "selected-top", "colors_verified": True, "colors": ["#ec2020"]}],
                },
            },
        }
        with mock.patch("core.bitmoji_config.load_catalog_raw", return_value=catalog), \
             mock.patch("core.bitmoji_config.load_models", return_value={}) as load_models, \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020") as resolve:
            result = await stub.pick_configured_color_option(
                "p1", "M", "tops", selected_option_id="selected-top",
            )

        self.assertTrue(result)
        load_models.assert_called_once_with()
        resolve.assert_called_once_with("M", "tops", {}, "selected-top")
        self.assertEqual(ctx.evaluated, ["#ec2020"])


if __name__ == "__main__":
    unittest.main()
