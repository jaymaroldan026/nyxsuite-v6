# Nyxmoji Live Selector Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make Nyxmoji select the exact live Bitmoji option, use its real PNG/render data, and expose or apply colours only where the selected garment supports them.

**Architecture:** The catalog is the shared contract among the live scanner, Nyxmoji UI, and runner. Each garment option retains its live PNG, a selector built for its actual tile, exact body-render parameters, and per-swatch render variants. A browser-safe helper derives valid colours and preview parameters from that catalog; Python applies the same validation.

**Tech Stack:** Python 3, unittest, Playwright CDP, Bitmoji preview URLs, vanilla JavaScript, Node built-in test runner.

---

### Task 0: Create the isolated test environment

**Files:**

- Create: /tmp/nyxmoji-selector-audit-venv/ (outside Git)
- Test: existing targeted tests

- [ ] **Step 1: Create the temporary environment and install requirements**

    python3 -m venv /tmp/nyxmoji-selector-audit-venv
    /tmp/nyxmoji-selector-audit-venv/bin/python -m pip install --upgrade pip
    /tmp/nyxmoji-selector-audit-venv/bin/python -m pip install -r requirements.txt

Expected: exit 0. The virtual environment is outside the worktree and untracked.

- [ ] **Step 2: Prove the targeted baseline**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_bitmoji_config_catalog tests.test_outfit_color_apply tests.test_outfit_fallback -v

Expected: all baseline tests pass. If a test fails, stop and diagnose before changing code.

### Task 1: Make catalog records item-aware and correct garment tile selectors

**Files:**

- Modify: core/bitmoji_config.py:36-238,390-512
- Modify: tests/test_bitmoji_config_catalog.py

- [ ] **Step 1: Write failing catalog-contract tests**

Add imports for _normalize_catalog, build_selector, option_colors, option_render, and sanitize_models. Add these tests:

    def test_garment_selector_targets_mix_and_match_tile(self):
        selector = build_selector("footwear", "1062")
        self.assertIn("mix-and-match-container", selector)
        self.assertIn("/avatar/footwear?", selector)
        self.assertIn("footwear=1062", selector)

    def test_colourless_garment_keeps_no_colours(self):
        raw = {"features": {"tops": {"type": "outfit", "options": [
            {"id": "plain", "colors": []},
        ]}}}
        self.assertEqual(option_colors("tops", "plain", _normalize_catalog(raw)), [])

    def test_option_render_uses_the_live_colour_variant(self):
        catalog = {"features": {"footwear": {"options": [{
            "id": "1062", "colors": ["#ec2020"],
            "render": {
                "params": {"footwear": "1062"},
                "colour_variants": {"#ec2020": {"footwear_tone1": "16031775"}},
            },
        }]}}}
        self.assertEqual(
            option_render("footwear", "1062", "#ec2020", catalog),
            {"footwear": "1062", "footwear_tone1": "16031775"},
        )

    def test_sanitize_models_drops_unsupported_fixed_colour(self):
        catalog = {"features": {"tops": {"options": [{"id": "plain", "colors": []}]}}}
        models = {"M": {"tops": {"mode": "fixed", "id": "plain", "color": "#ec2020"}}}
        self.assertEqual(sanitize_models(models, catalog), {"M": {"tops": {"mode": "fixed", "id": "plain"}}})

- [ ] **Step 2: Run the test to verify red**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_bitmoji_config_catalog -v

Expected: failure identifies missing helpers, the generic Outfits colour backfill, and head-trait garment selectors.

- [ ] **Step 3: Implement the minimal catalog contract**

Change every clothing pattern to target the true mix-and-match tile. The five core patterns must be:

    tops: xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top={id}')]]
    bottoms: xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom={id}')]]
    dresses: xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/one_piece?') and contains(@src,'bottom={id}')]]
    footwear: xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear={id}')]]
    outerwear: xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/outerwear?') and contains(@src,'outerwear={id}')]]

Add these helpers:

    def catalog_option(feature, option_id, catalog=None):
        catalog = catalog or load_catalog_raw()
        options = ((catalog.get("features", {}).get(feature, {}) or {}).get("options") or [])
        return next((item for item in options if str(item.get("id")) == str(option_id)), None)

    def option_colors(feature, option_id, catalog=None):
        item = catalog_option(feature, option_id, catalog) or {}
        return [str(color).lower() for color in item.get("colors", []) if str(color).strip()]

    def option_render(feature, option_id, color=None, catalog=None):
        item = catalog_option(feature, option_id, catalog) or {}
        render = item.get("render") or {}
        params = {str(key): str(value) for key, value in (render.get("params") or {}).items()}
        params.update((render.get("colour_variants") or {}).get(str(color or "").lower(), {}))
        return params

    def sanitize_models(models, catalog=None):
        catalog = catalog or load_catalog_raw()
        normalized = {}
        for model, features in (models or {}).items():
            entries = {}
            for feature, selection in (features or {}).items():
                if feature not in FEATURES or not isinstance(selection, dict):
                    continue
                mode = str(selection.get("mode") or "").lower()
                if mode == "fixed" and str(selection.get("id") or "").strip():
                    item_id = str(selection["id"]).strip()
                    entry = {"mode": "fixed", "id": item_id}
                    colors = option_colors(feature, item_id, catalog)
                    color = str(selection.get("color") or "").lower()
                    if color in colors:
                        entry["color"] = color
                    entries[feature] = entry
                if mode == "random":
                    pool = [str(item).strip() for item in selection.get("pool", []) if str(item).strip()]
                    if pool:
                        allowed = {color for item in pool for color in option_colors(feature, item, catalog)}
                        colors = [str(color).lower() for color in selection.get("colors", []) if str(color).lower() in allowed]
                        entries[feature] = {"mode": "random", "pool": pool, **({"colors": colors} if colors else {})}
            if entries:
                normalized[model] = entries
        return normalized

Remove the Outfits-to-Tops generic colour backfill. Keep a missing live colour picker as an empty list. Make save_models call sanitize_models with load_catalog_raw; fixed colors must be supported by the chosen id and random colors must be inside the selected-pool union.

- [ ] **Step 4: Run the test to verify green**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_bitmoji_config_catalog -v

Expected: all catalog contract tests pass.

- [ ] **Step 5: Commit Task 1**

    git add core/bitmoji_config.py tests/test_bitmoji_config_catalog.py
    git commit -m "fix: make Nyxmoji garment metadata item-aware"

### Task 2: Scan each live garment tile without saving and record exact render variants

**Files:**

- Modify: tools/scan_bitmoji_live.py:135-274,319-402
- Create: tests/test_bitmoji_live_scan.py

- [ ] **Step 1: Write failing scanner-helper tests**

    from tools.scan_bitmoji_live import parse_preview_render, normalize_colour_map

    def test_parse_preview_render_keeps_item_and_all_tone_parameters(self):
        url = ("https://preview.bitmoji.com/bm-preview/v3/avatar/top?"
               "top=897&top_tone1=3171228&top_tone2=4690663")
        self.assertEqual(parse_preview_render(url, "top"), {
            "params": {"top": "897"},
            "colour_params": ["top_tone1", "top_tone2"],
        })

    def test_parse_preview_render_marks_colourless_item(self):
        url = "https://preview.bitmoji.com/bm-preview/v3/avatar/footwear?footwear=plain"
        self.assertEqual(parse_preview_render(url, "footwear"), {
            "params": {"footwear": "plain"}, "colour_params": [],
        })

    def test_normalize_colour_map_uses_only_visible_picker_values(self):
        self.assertEqual(normalize_colour_map(["#EC2020", "#ec2020", "invalid"]), ["#ec2020"])

- [ ] **Step 2: Run the test to verify red**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_bitmoji_live_scan -v

Expected: import failures prove the scanner helpers are absent.

- [ ] **Step 3: Implement per-tile capture and atomic catalog publication**

Add pure helpers:

    def parse_preview_render(url, item_param):
        query = parse_qs(urlparse(url).query)
        params = {item_param: query[item_param][0]} if query.get(item_param) else {}
        tones = sorted(key for key in query if re.fullmatch(r"[a-z_]+_tone\d+", key))
        return {"params": params, "colour_params": tones}

    def normalize_colour_map(colors):
        output = []
        for color in colors:
            value = str(color or "").strip().lower()
            if re.fullmatch(r"#[0-9a-f]{6}", value) and value not in output:
                output.append(value)
        return output

Replace the one-time outfit_palette capture. For every garment tile, click it without invoking Save, wait for the picker state, collect only visible swatches, and read the live avatar-body preview after each swatch click. Store:

    {
        "id": item_id,
        "preview": tile_preview_url,
        "colors": ["#ec2020"],
        "render": {
            "params": {"top": item_id},
            "colour_variants": {
                "#ec2020": {"top_tone1": "3171228", "top_tone2": "4690663"},
            },
        },
    }

A tile with no picker has empty colors and empty colour_variants. Default mode writes only a JSON audit report; require --write to atomically replace the runtime catalog via CATALOG_PATH.with_suffix(".json.tmp").

- [ ] **Step 4: Run the test to verify green**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_bitmoji_live_scan -v

Expected: all scanner helper tests pass.

- [ ] **Step 5: Commit Task 2**

    git add tools/scan_bitmoji_live.py tests/test_bitmoji_live_scan.py
    git commit -m "fix: scan Nyxmoji garment colours per live tile"

### Task 3: Show only item-supported swatches and build stage previews from live metadata

**Files:**

- Create: webui/nyxmoji_helpers.js
- Create: tests/test_nyxmoji_helpers.cjs
- Modify: webui/index.html:8-10
- Modify: webui/dashboard.js:1282-1806

- [ ] **Step 1: Write the failing Node helper test**

    const test = require("node:test");
    const assert = require("node:assert/strict");
    const helpers = require("../webui/nyxmoji_helpers.js");

    const feature = { type: "outfit", options: [
      { id: "plain", colors: [], render: { params: { top: "plain" }, colour_variants: {} } },
      { id: "red", colors: ["#ec2020"], render: {
        params: { top: "red" },
        colour_variants: { "#ec2020": { top_tone1: "3171228" } },
      }},
    ] };

    test("fixed colours belong only to the selected garment", () => {
      assert.deepEqual(helpers.availableColours(feature, { mode: "fixed", id: "plain" }), []);
      assert.deepEqual(helpers.availableColours(feature, { mode: "fixed", id: "red" }), ["#ec2020"]);
    });

    test("random colours are the selected pool union", () => {
      assert.deepEqual(helpers.availableColours(feature, { mode: "random", pool: ["plain", "red"] }), ["#ec2020"]);
    });

    test("preview uses selected live colour variant", () => {
      assert.deepEqual(helpers.optionRenderParams(feature, "red", "#ec2020"), { top: "red", top_tone1: "3171228" });
    });

- [ ] **Step 2: Run the test to verify red**

    node --test tests/test_nyxmoji_helpers.cjs

Expected: MODULE_NOT_FOUND for the helper module.

- [ ] **Step 3: Implement the browser-safe helper**

Create webui/nyxmoji_helpers.js:

    (function (root, factory) {
      const api = factory();
      if (typeof module === "object" && module.exports) module.exports = api;
      root.NyxmojiHelpers = api;
    })(globalThis, function () {
      const normalized = value => String(value || "").trim().toLowerCase();
      const optionById = (feature, id) => (feature?.options || []).find(option => String(option.id) === String(id));
      const coloursForOption = option => [...new Set((option?.colors || []).map(normalized).filter(Boolean))];
      const availableColours = (feature, selection) => {
        const ids = selection?.mode === "fixed" ? [selection.id] : (selection?.pool || []);
        return [...new Set(ids.flatMap(id => coloursForOption(optionById(feature, id))))];
      };
      const optionRenderParams = (feature, id, colour) => {
        const render = optionById(feature, id)?.render || {};
        return { ...(render.params || {}), ...((render.colour_variants || {})[normalized(colour)] || {}) };
      };
      return { optionById, availableColours, optionRenderParams };
    });

Load it immediately before dashboard.js in webui/index.html. In dashboard.js remove BM_OUTFIT_COLORS and bmOutfitColors. Use NyxmojiHelpers.availableColours for fixed panels, random unions, bulk action, Shuffle, and Recommend. Omit the whole colour block when no valid colours exist. When selected item or random pool changes, discard saved colours outside the new supported set.

In buildAvatarUrl, use NyxmojiHelpers.optionRenderParams(feat, id, color) and set every returned parameter. Retain the existing renderParams fallback for non-garment feature types. Keep the option thumbnail src as option.preview.

- [ ] **Step 4: Run the UI tests to verify green**

    node --test tests/test_nyxmoji_helpers.cjs
    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_dashboard_adspower_control_mode -v

Expected: all Node tests pass and the existing dashboard contract remains green.

- [ ] **Step 5: Commit Task 3**

    git add webui/nyxmoji_helpers.js tests/test_nyxmoji_helpers.cjs webui/index.html webui/dashboard.js
    git commit -m "fix: render Nyxmoji colours from live garment metadata"

### Task 4: Use the actual selected garment to decide runtime colour application

**Files:**

- Modify: core/bitmoji/outfit_flow.py:344-367,1397-1761
- Modify: tests/test_outfit_color_apply.py
- Modify: tests/test_outfit_fallback.py

- [ ] **Step 1: Add failing runtime no-picker tests**

    async def test_colourless_item_skips_picker_and_random_fallback(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.option_colors", return_value=[]):
            result = await stub.pick_configured_color_option("p1", "M", "footwear", option_id="plain")
        self.assertFalse(result)
        self.assertFalse(stub.random_called)
        self.assertEqual(ctx.evaluated, [])

    async def test_supported_item_applies_only_supported_configured_colour(self):
        ctx = _FakeCtx(clicked=True)
        stub = _StubColor(ctx)
        with mock.patch("core.bitmoji_config.option_colors", return_value=["#ec2020"]), \
             mock.patch("core.bitmoji_config.resolve_option_color", return_value="#ec2020"):
            result = await stub.pick_configured_color_option("p1", "M", "tops", option_id="897")
        self.assertTrue(result)
        self.assertEqual(ctx.evaluated, ["#ec2020"])

Update fallback assertions to require _apply_outfit_piece to return the selector string that actually clicked. The returned string remains truthy for existing callers.

- [ ] **Step 2: Run the targeted test to verify red**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_outfit_color_apply tests.test_outfit_fallback -v

Expected: failure shows that option_id is not accepted and colourless items still use the generic random-colour path.

- [ ] **Step 3: Implement item-aware runtime colour guard**

Add /avatar/outerwear? to is_outfit_selector and panel scan markers. Make _apply_outfit_piece and _apply_pool_fallback_piece return the successful selector string. Parse the selected id from that selector and pass it to the colour method:

    selected = await self._apply_outfit_piece(
        "categories.tops", top_entry["selector"], profile_id,
        fallback_param="top", blocked_ids=BLOCKED_TOP_IDS,
        fallback_pool=outfit.get("top_pool"),
    )
    await self.pick_configured_color_option(
        profile_id, model, ("tops", "outfits"),
        option_id=self.outfit_option_id(selected, "top"),
        outfit_seed=outfit_seed,
        preferred_color=top_entry.get("preferred_color"),
    )

Add keyword-only option_id to pick_configured_color_option. For each candidate feature check option_colors(feature, option_id). If the catalog knows the item and its colour list is empty, return False immediately. If the configured colour is outside the known list, log and return False. Unknown legacy items retain the existing visible-picker check; never click an absent picker and never use random-colour fallback for a known colourless item.

- [ ] **Step 4: Run targeted test to verify green**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_outfit_color_apply tests.test_outfit_fallback -v

Expected: all runtime colour and fallback tests pass.

- [ ] **Step 5: Commit Task 4**

    git add core/bitmoji/outfit_flow.py tests/test_outfit_color_apply.py tests/test_outfit_fallback.py
    git commit -m "fix: skip Nyxmoji colour for colourless garments"

### Task 5: Audit the supplied AdsPower profile without saving, then publish catalog data

**Files:**

- Write (ignored runtime data only): data/bitmoji_catalog.json
- Output (ignored): output/playwright/nyxmoji-selector-audit.json

- [ ] **Step 1: Run the read-only audit with profile k1f2la8v**

    /tmp/nyxmoji-selector-audit-venv/bin/python tools/scan_bitmoji_live.py k1f2la8v --report output/playwright/nyxmoji-selector-audit.json

Expected: report records every selector count, real PNG URLs, per-tile colours, and colourless items. It must not save the avatar or overwrite the catalog.

- [ ] **Step 2: Assert audit safety and selector success**

    /tmp/nyxmoji-selector-audit-venv/bin/python - <<'PY'
    import json
    from pathlib import Path
    report = json.loads(Path("output/playwright/nyxmoji-selector-audit.json").read_text())
    assert report["save_actions"] == 0
    assert not report["selector_failures"], report["selector_failures"]
    print("audited selectors:", report["selector_count"])
    print("colourless options:", report["colourless_option_count"])
    PY

Expected: both assertions pass. If AdsPower permission, attachment, authentication, or live UI shape blocks the audit, leave the catalog unchanged and report the exact blocker.

- [ ] **Step 3: Regenerate local catalog only after clean audit**

    /tmp/nyxmoji-selector-audit-venv/bin/python tools/scan_bitmoji_live.py k1f2la8v --write

Expected: scanner atomically writes the local ignored catalog with real PNGs, per-item colours, and exact render variants; it reports zero save actions.

### Task 6: Final verification and review

**Files:**

- Verify: all modified source and tests

- [ ] **Step 1: Run complete Nyxmoji regression checks**

    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest discover -s tests -p 'test_bitmoji*.py' -v
    /tmp/nyxmoji-selector-audit-venv/bin/python -m unittest tests.test_outfit_color_apply tests.test_outfit_fallback tests.test_nyx_auth_phase_routing -v
    node --test tests/test_nyxmoji_helpers.cjs
    git diff --check

Expected: every command exits 0 with no whitespace errors.

- [ ] **Step 2: Check implementation scope and artifact hygiene**

    git diff 22599cb..HEAD -- core/bitmoji_config.py core/bitmoji/outfit_flow.py tools/scan_bitmoji_live.py webui/index.html webui/dashboard.js webui/nyxmoji_helpers.js tests/
    git status --short

Expected: no generated catalog or audit report is tracked, every design requirement has code coverage, and the worktree is clean after commits.

- [ ] **Step 3: Commit only a tracked verification adjustment if needed**

    git add -A
    git commit -m "test: verify Nyxmoji live selector repair"

Expected: execute this only when verification requires a tracked adjustment; otherwise leave history at the Task 4 commit.
