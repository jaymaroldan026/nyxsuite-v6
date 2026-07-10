"""Catalog normalization + colour resolution for the Nyxmoji editor.

Covers the v6.0.9 fixes:
  * ``outfits`` is a duplicate of ``tops`` — it is relabelled to make the overlap
    explicit and its (empty) per-option colours are backfilled from ``tops`` so
    its swatches and end-to-end colour apply work.
  * the Outfits preview param was ``outfit`` (which ``/avatar/body`` ignores) and
    is now ``top`` so the live preview renders.
  * ``resolve_option_color`` returns the operator's configured colour (fixed, or a
    random pick from the pool) that the bot now applies.
"""
import unittest

from core.bitmoji_config import (
    RENDER_PARAMS,
    _normalize_catalog,
    load_catalog_raw,
    render_param_map,
    resolve_option_color,
)


class NormalizeCatalogTests(unittest.TestCase):
    def _fake(self):
        return {
            "features": {
                "outfits": {
                    "label": "Outfits", "type": "outfit",
                    "options": [{"id": "1", "colors": []}, {"id": "2", "colors": []}],
                },
                "tops": {
                    "label": "Tops", "type": "outfit",
                    "options": [{"id": "1", "colors": ["#aaaaaa", "#bbbbbb"]},
                                {"id": "2", "colors": []}],
                },
            }
        }

    def test_relabels_and_backfills_colors(self):
        out = _normalize_catalog(self._fake())
        self.assertEqual(out["features"]["outfits"]["label"], "Outfits (Tops slot)")
        self.assertEqual(out["features"]["outfits"]["options"][0]["colors"], ["#aaaaaa", "#bbbbbb"])
        # id 2 had no colours in tops either — stays empty (nothing to backfill).
        self.assertEqual(out["features"]["outfits"]["options"][1]["colors"], [])

    def test_idempotent(self):
        once = _normalize_catalog(self._fake())
        twice = _normalize_catalog(once)
        self.assertEqual(twice["features"]["outfits"]["label"], "Outfits (Tops slot)")
        self.assertEqual(twice["features"]["outfits"]["options"][0]["colors"], ["#aaaaaa", "#bbbbbb"])

    def test_handles_missing_features(self):
        self.assertEqual(_normalize_catalog({}), {})
        self.assertEqual(_normalize_catalog({"features": {}}), {"features": {}})

    def test_real_catalog_outfits_has_colors_and_label(self):
        raw = load_catalog_raw()
        outfits = raw.get("features", {}).get("outfits")
        if not outfits:  # catalog not present in this environment
            self.skipTest("bitmoji_catalog.json has no outfits feature")
        self.assertIn("Tops", outfits.get("label", ""))
        self.assertTrue(any(o.get("colors") for o in outfits.get("options", [])),
                        "expected at least one outfits option to have backfilled colours")


class RenderParamTests(unittest.TestCase):
    def test_outfits_preview_param_is_top(self):
        self.assertEqual(RENDER_PARAMS["outfits"], ("top", False))
        self.assertEqual(RENDER_PARAMS["tops"], ("top", False))

    def test_render_param_map_shape(self):
        m = render_param_map()
        self.assertEqual(m["outfits"], {"param": "top", "color": False})


class ResolveOptionColorTests(unittest.TestCase):
    def test_fixed_returns_configured_color(self):
        models = {"M": {"tops": {"mode": "fixed", "id": "5", "color": "#ec2020"}}}
        self.assertEqual(resolve_option_color("M", "tops", models), "#ec2020")

    def test_fixed_without_color_returns_none(self):
        models = {"M": {"tops": {"mode": "fixed", "id": "5"}}}
        self.assertIsNone(resolve_option_color("M", "tops", models))

    def test_random_picks_from_pool(self):
        models = {"M": {"tops": {"mode": "random", "pool": ["1"], "colors": ["#111111", "#222222"]}}}
        for _ in range(30):
            self.assertIn(resolve_option_color("M", "tops", models), ["#111111", "#222222"])

    def test_random_without_colors_returns_none(self):
        models = {"M": {"tops": {"mode": "random", "pool": ["1", "2"]}}}
        self.assertIsNone(resolve_option_color("M", "tops", models))

    def test_unconfigured_returns_none(self):
        models = {"M": {"tops": {"mode": "random", "pool": ["1"], "colors": ["#111111"]}}}
        self.assertIsNone(resolve_option_color("M", "bottoms", models))
        self.assertIsNone(resolve_option_color("OTHER", "tops", models))


if __name__ == "__main__":
    unittest.main()
