"""Item-aware catalog and colour resolution for the Nyxmoji editor."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.bitmoji_config as bitmoji_config
from core.bitmoji_config import (
    FEATURES,
    RENDER_PARAMS,
    _normalize_catalog,
    _xpath_string_literal,
    build_selector,
    catalog_option,
    option_colors,
    option_render,
    render_param_map,
    resolve_option,
    resolve_option_color,
    sanitize_models,
    save_models,
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

    def test_preserves_feature_labels_and_never_backfills_colours(self):
        out = _normalize_catalog(self._fake())
        self.assertEqual(out["features"]["outfits"]["label"], "Outfits")
        self.assertEqual(out["features"]["outfits"]["options"][0]["colors"], [])
        self.assertEqual(out["features"]["outfits"]["options"][1]["colors"], [])

    def test_idempotent(self):
        once = _normalize_catalog(self._fake())
        twice = _normalize_catalog(once)
        self.assertEqual(twice, once)

    def test_handles_missing_features(self):
        self.assertEqual(_normalize_catalog({}), {})
        self.assertEqual(_normalize_catalog({"features": {}}), {"features": {}})

    def test_option_render_merges_only_the_selected_garment_colour_variant(self):
        catalog = {
            "features": {
                "footwear": {
                    "options": [{
                        "id": "1062", "colors": ["#ec2020", "#010203"], "colors_verified": True,
                        "render": {
                            "params": {"footwear": "1062"},
                            "colour_variants": {"#ec2020": {"footwear_tone1": "16031775"}},
                            "color_variants": {"#010203": {"footwear_tone1": "66051"}},
                        },
                    }, {
                        "id": "other", "colors": ["#ec2020"], "colors_verified": True,
                        "render": {
                            "params": {"footwear": "other"},
                            "colour_variants": {"#ec2020": {"footwear_tone1": "999"}},
                        },
                    }],
                },
            },
        }
        self.assertEqual(catalog_option("footwear", "1062", catalog)["id"], "1062")
        self.assertEqual(option_colors("footwear", "1062", catalog), ["#ec2020", "#010203"])
        # The former third positional catalog argument remains supported.
        self.assertEqual(option_render("footwear", "1062", catalog), {"footwear": "1062"})
        self.assertEqual(option_render("footwear", "1062", "#EC2020", catalog),
                         {"footwear": "1062", "footwear_tone1": "16031775"})
        self.assertEqual(option_render("footwear", "1062", color="#010203", catalog=catalog),
                         {"footwear": "1062", "footwear_tone1": "66051"})
        self.assertEqual(option_render("footwear", "1062", "#ffffff", catalog),
                         {"footwear": "1062"})
        self.assertEqual(option_render("footwear", "missing", "#ec2020", catalog), {})

    def test_catalog_helpers_accept_a_feature_map(self):
        feature_map = {"tops": {"options": [{"id": "shirt", "colors": ["#123456"]}]}}
        self.assertEqual(option_colors("tops", "shirt", feature_map), ["#123456"])


class GarmentSelectorTests(unittest.TestCase):
    def test_every_apparel_feature_targets_its_live_mix_and_match_tile(self):
        expected = {
            "outfits": ("/avatar/top?", "top"),
            "tops": ("/avatar/top?", "top"),
            "bottoms": ("/avatar/bottom?", "bottom"),
            "dresses": ("/avatar/one_piece?", "bottom"),
            "footwear": ("/avatar/footwear?", "footwear"),
            "outerwear": ("/avatar/outerwear?", "outerwear"),
        }
        for feature, (preview_marker, parameter) in expected.items():
            with self.subTest(feature=feature):
                selector = build_selector(feature, "123")
                self.assertIn("mix-and-match-container", selector)
                self.assertNotIn("head-trait-container", selector)
                self.assertIn(preview_marker, selector)
                self.assertIn(f"concat('&{parameter}=', '123', '&')", selector)

    def test_selector_uses_a_safe_xpath_literal_for_quoted_option_ids(self):
        option_id = "shirt'\""
        literal = _xpath_string_literal(option_id)
        self.assertEqual(literal, """concat('shirt', "'", '"')""")

        selector = build_selector("tops", option_id)
        self.assertIn(f"concat('&top=', {literal}, '&')", selector)
        self.assertNotIn(option_id, selector)
        self.assertNotIn("{id}", selector)

    def test_all_apparel_features_are_outfit_features(self):
        for feature in ("outfits", "tops", "bottoms", "dresses", "footwear", "outerwear"):
            with self.subTest(feature=feature):
                self.assertEqual(FEATURES[feature]["kind"], "outfit")


class ModelSanitizationTests(unittest.TestCase):
    def _catalog(self):
        return {
            "features": {
                "tops": {"options": [
                    {"id": "red", "colors": ["#ec2020", "#010203"], "colors_verified": True},
                    {"id": "plain", "colors": [], "colors_verified": True},
                    {"id": "blue", "colors": ["#010203"], "colors_verified": True},
                ]},
            },
        }

    def test_fixed_colours_are_kept_only_when_supported_by_that_item(self):
        models = {"M": {"tops": {"mode": "fixed", "id": "red", "color": "#ec2020"}}}
        self.assertEqual(sanitize_models(models, self._catalog()), models)

        invalid = {"M": {"tops": {"mode": "fixed", "id": "red", "color": "#ffffff"}}}
        self.assertEqual(sanitize_models(invalid, self._catalog()),
                         {"M": {"tops": {"mode": "fixed", "id": "red"}}})

    def test_colourless_items_remove_their_persisted_colours(self):
        fixed = {"M": {"tops": {"mode": "fixed", "id": "plain", "color": "#ec2020"}}}
        self.assertEqual(sanitize_models(fixed, self._catalog()),
                         {"M": {"tops": {"mode": "fixed", "id": "plain"}}})

        random_selection = {"M": {"tops": {
            "mode": "random", "pool": ["plain"], "colors": ["#ec2020"],
        }}}
        self.assertEqual(sanitize_models(random_selection, self._catalog()),
                         {"M": {"tops": {"mode": "random", "pool": ["plain"]}}})

    def test_unverified_empty_colours_preserve_fixed_and_random_configuration(self):
        catalog = {"features": {"tops": {"options": [{"id": "not-yet-audited", "colors": []}]}}}
        fixed = {"M": {"tops": {
            "mode": "fixed", "id": "not-yet-audited", "color": "#ec2020",
        }}}
        random_selection = {"M": {"tops": {
            "mode": "random", "pool": ["not-yet-audited"], "colors": ["#ec2020"],
        }}}
        self.assertEqual(sanitize_models(fixed, catalog), fixed)
        self.assertEqual(sanitize_models(random_selection, catalog), random_selection)

    def test_unverified_nonempty_colours_preserve_fixed_and_random_configuration(self):
        catalog = {"features": {"tops": {"options": [
            {"id": "legacy-palette", "colors": ["#111111"]},
        ]}}}
        fixed = {"M": {"tops": {
            "mode": "fixed", "id": "legacy-palette", "color": "#ffffff",
        }}}
        random_selection = {"M": {"tops": {
            "mode": "random", "pool": ["legacy-palette"], "colors": ["#ffffff"],
        }}}
        self.assertEqual(sanitize_models(fixed, catalog), fixed)
        self.assertEqual(sanitize_models(random_selection, catalog), random_selection)

    def test_random_colours_use_the_union_of_known_pool_options(self):
        models = {"M": {"tops": {
            "mode": "random", "pool": ["red", "blue"],
            "colors": ["#ec2020", "#010203"],
        }}}
        self.assertEqual(sanitize_models(models, self._catalog()), {"M": {"tops": {
            "mode": "random", "pool": ["red", "blue"], "colors": ["#ec2020", "#010203"],
        }}})

    def test_random_colours_are_preserved_when_any_pool_item_is_unknown(self):
        models = {"M": {"tops": {
            "mode": "random", "pool": ["red", "not-in-catalog"], "colors": ["#ffffff"],
        }}}
        self.assertEqual(sanitize_models(models, self._catalog()), models)

    def test_catalog_unavailability_does_not_discard_existing_colours(self):
        models = {"M": {"tops": {"mode": "fixed", "id": "red", "color": "#ec2020"}}}
        self.assertEqual(sanitize_models(models, {}), models)

    def test_save_models_persists_sanitized_colours(self):
        models = {"M": {"tops": {"mode": "fixed", "id": "plain", "color": "#ec2020"}}}
        catalog = {"features": {"tops": {"options": [
            {"id": "plain", "colors": [], "colors_verified": True},
        ]}}}
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            models_path = data_dir / "bitmoji_models.json"
            with mock.patch.object(bitmoji_config, "DATA_DIR", data_dir), \
                 mock.patch.object(bitmoji_config, "MODELS_PATH", models_path), \
                 mock.patch.object(bitmoji_config, "load_catalog_raw", return_value=catalog):
                self.assertEqual(save_models(models), {"M": {"tops": {"mode": "fixed", "id": "plain"}}})
            self.assertEqual(json.loads(models_path.read_text(encoding="utf-8")),
                             {"M": {"tops": {"mode": "fixed", "id": "plain"}}})

    def test_save_models_rejects_non_mapping_without_writing_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            models_path = data_dir / "bitmoji_models.json"
            existing = {"M": {"tops": {"mode": "fixed", "id": "5"}}}
            models_path.write_text(json.dumps(existing), encoding="utf-8")
            with mock.patch.object(bitmoji_config, "DATA_DIR", data_dir), \
                 mock.patch.object(bitmoji_config, "MODELS_PATH", models_path):
                with self.assertRaisesRegex(ValueError, "models must be a mapping"):
                    save_models(["malformed"])
                with self.assertRaisesRegex(ValueError, "models must be a mapping"):
                    sanitize_models("malformed")
                self.assertEqual(json.loads(models_path.read_text(encoding="utf-8")), existing)
                self.assertEqual(save_models({}), {})
            self.assertEqual(json.loads(models_path.read_text(encoding="utf-8")), {})

    def test_malformed_random_collections_are_ignored_without_throwing(self):
        malformed = {"M": {"tops": {"mode": "random", "pool": "not-a-list", "colors": {"#111111": 1}}}}
        self.assertEqual(sanitize_models(malformed, {}), {})
        self.assertIsNone(resolve_option("M", "tops", malformed))
        self.assertIsNone(resolve_option_color("M", "tops", malformed))

        malformed["M"]["tops"] = {"mode": "random", "pool": 7, "colors": 8}
        self.assertEqual(sanitize_models(malformed, {}), {})
        self.assertIsNone(resolve_option("M", "tops", malformed))
        self.assertIsNone(resolve_option_color("M", "tops", malformed))


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

    def test_selected_random_item_limits_colour_to_its_own_catalog_entry(self):
        catalog = {"features": {"tops": {"options": [
            {"id": "A", "colors": ["#111111"], "colors_verified": True},
            {"id": "B", "colors": ["#222222"], "colors_verified": True},
        ]}}}
        models = {"M": {"tops": {
            "mode": "random", "pool": ["A", "B"], "colors": ["#111111", "#222222"],
        }}}
        self.assertEqual(resolve_option_color("M", "tops", models, option_id="A", catalog=catalog),
                         "#111111")
        self.assertEqual(resolve_option_color("M", "tops", models, option_id="B", catalog=catalog),
                         "#222222")

    def test_known_colourless_fixed_item_returns_none(self):
        catalog = {"features": {"tops": {"options": [
            {"id": "plain", "colors": [], "colors_verified": True},
        ]}}}
        models = {"M": {"tops": {"mode": "fixed", "id": "plain", "color": "#111111"}}}
        self.assertIsNone(resolve_option_color("M", "tops", models, option_id="plain", catalog=catalog))

    def test_unverified_empty_selected_item_keeps_legacy_runtime_colour(self):
        catalog = {"features": {"tops": {"options": [{"id": "not-yet-audited", "colors": []}]}}}
        models = {"M": {"tops": {
            "mode": "random", "pool": ["not-yet-audited"], "colors": ["#111111"],
        }}}
        self.assertEqual(resolve_option_color(
            "M", "tops", models, option_id="not-yet-audited", catalog=catalog,
        ), "#111111")

    def test_unverified_nonempty_selected_item_keeps_legacy_runtime_colour(self):
        catalog = {"features": {"tops": {"options": [
            {"id": "legacy-palette", "colors": ["#111111"]},
        ]}}}
        fixed = {"M": {"tops": {
            "mode": "fixed", "id": "legacy-palette", "color": "#ffffff",
        }}}
        random_selection = {"M": {"tops": {
            "mode": "random", "pool": ["legacy-palette"], "colors": ["#ffffff"],
        }}}
        self.assertEqual(resolve_option_color(
            "M", "tops", fixed, option_id="legacy-palette", catalog=catalog,
        ), "#ffffff")
        self.assertEqual(resolve_option_color(
            "M", "tops", random_selection, option_id="legacy-palette", catalog=catalog,
        ), "#ffffff")

    def test_unconfigured_returns_none(self):
        models = {"M": {"tops": {"mode": "random", "pool": ["1"], "colors": ["#111111"]}}}
        self.assertIsNone(resolve_option_color("M", "bottoms", models))
        self.assertIsNone(resolve_option_color("OTHER", "tops", models))


if __name__ == "__main__":
    unittest.main()
