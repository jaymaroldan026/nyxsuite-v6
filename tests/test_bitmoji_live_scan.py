"""Offline tests for the live Bitmoji catalog scanner's data handling."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCANNER_PATH = ROOT / "tools" / "scan_bitmoji_live.py"
SPEC = importlib.util.spec_from_file_location("nyxmoji_live_scan", SCANNER_PATH)
scan = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(scan)


class PreviewDeltaTests(unittest.TestCase):
    def test_preview_delta_keeps_only_changed_meaningful_scalar_params(self):
        base = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "top=10&gender=1&style=5&scale=3&client=web&same=unchanged"
        )
        current = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "top=22&top_tone1=16031775&gender=1&style=5&scale=1&"
            "rotation=0&client=web&same=unchanged"
        )

        self.assertEqual(
            scan.preview_delta(base, current),
            {"top": "22", "top_tone1": "16031775"},
        )

    def test_body_tone_colours_converts_decimal_garment_tones_to_hex(self):
        body = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "top=897&top_tone1=3171228&bottom=356&bottom_tone1=11801878"
        )

        self.assertEqual(scan.body_tone_colours("tops", body), {"#30639c"})


class OutfitRenderFilterTests(unittest.TestCase):
    def test_top_render_drops_a_stale_bottom_from_a_previous_dress(self):
        params = {
            "top": "1062",
            "top_tone1": "16031775",
            "bottom": "632",
            "bottom_tone1": "77",
        }

        self.assertEqual(
            scan.filter_outfit_render_params("tops", params),
            {"top": "1062", "top_tone1": "16031775"},
        )

    def test_dress_render_retains_its_paired_top_and_bottom_params(self):
        params = {"top": "632", "top_tone1": "10", "bottom": "632", "bottom_tone1": "20"}

        self.assertEqual(scan.filter_outfit_render_params("dresses", params), params)

    def test_dress_preview_drops_an_unadvertised_stale_sibling(self):
        params = {"top": "632", "top_tone1": "10", "bottom": "old", "bottom_tone1": "20"}
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632"

        self.assertEqual(
            scan.filter_outfit_render_params("dresses", params, preview),
            {"top": "632", "top_tone1": "10"},
        )

    def test_paired_preview_without_garment_params_persists_nothing(self):
        params = {"top": "632", "top_tone1": "10", "bottom": "old", "bottom_tone1": "20"}
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?gender=1"

        self.assertEqual(scan.filter_outfit_render_params("dresses", params, preview), {})

    def test_top_only_outfit_preview_rejects_stale_bottom_params(self):
        params = {"top": "1062", "top_tone1": "10", "bottom": "632", "bottom_tone1": "20"}
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"

        self.assertEqual(
            scan.filter_outfit_render_params("outfits", params, preview),
            {"top": "1062", "top_tone1": "10"},
        )

    def test_paired_outfit_preview_keeps_top_and_bottom_params(self):
        params = {"top": "632", "top_tone1": "10", "bottom": "632", "bottom_tone1": "20"}
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632&bottom=632"

        self.assertEqual(scan.filter_outfit_render_params("outfits", params, preview), params)


class OutfitOptionAssemblyTests(unittest.TestCase):
    def test_each_garment_keeps_its_own_completed_colour_variants(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        red = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "gender=1&top=1062&top_tone1=16031775"
        )
        blue = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "gender=1&top=1062&top_tone1=123"
        )
        option = scan.assemble_outfit_option(
            "1062",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062",
            base,
            {"#EC2020": red, "#010203": blue},
            complete=True,
        )

        self.assertEqual(option["colors"], ["#ec2020", "#010203"])
        self.assertTrue(option["colors_verified"])
        self.assertEqual(option["render"]["params"], {"top": "1062"})
        self.assertEqual(
            option["render"]["colour_variants"]["#ec2020"],
            {"top": "1062", "top_tone1": "16031775"},
        )
        self.assertEqual(
            option["render"]["colour_variants"]["#010203"],
            {"top": "1062", "top_tone1": "123"},
        )

    def test_colourless_completed_garment_is_authoritatively_verified(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        option = scan.assemble_outfit_option(
            "plain",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/footwear?footwear=plain",
            base,
            {},
            complete=True,
        )

        self.assertEqual(option["colors"], [])
        self.assertTrue(option["colors_verified"])
        self.assertNotIn("colour_variants", option["render"])

    def test_partial_garment_scan_cannot_be_marked_verified(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        option = scan.assemble_outfit_option(
            "1062",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062",
            base,
            {"#ec2020": "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062"},
            complete=False,
            error="picker disappeared after the first swatch",
        )

        self.assertFalse(option["colors_verified"])
        self.assertEqual(option["scan_error"], "picker disappeared after the first swatch")

    def test_selected_top_params_survive_when_the_item_already_matches_base_avatar(self):
        body = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=1062"
        option = scan.assemble_outfit_option(
            "1062",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062",
            body,
            {},
            complete=True,
            feature="tops",
            body_preview=body,
        )

        self.assertEqual(option["render"]["params"], {"top": "1062"})

    def test_selected_dress_pair_survives_when_it_already_matches_base_avatar(self):
        body = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=632&bottom=632"
        option = scan.assemble_outfit_option(
            "632",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632&bottom=632",
            body,
            {},
            complete=True,
            feature="dresses",
            body_preview=body,
        )

        self.assertEqual(option["render"]["params"], {"top": "632", "bottom": "632"})


class OutfitScanCallPathTests(unittest.TestCase):
    def test_swatch_variant_match_allows_tone_params_to_change(self):
        previous = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=897&top_tone1=3171228"
        changed = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "top=897&top_tone1=11801878&top_tone2=4823115"
        )
        preview = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/top?"
            "top=897&top_tone1=3171228&top_tone2=4690663"
        )

        class Frame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return changed
                raise AssertionError(f"unexpected browser script: {script}")

        self.assertFalse(scan.body_matches_advertised_tile(changed, "top", "897", "tops", preview))
        self.assertTrue(
            scan.body_matches_advertised_tile(
                changed,
                "top",
                "897",
                "tops",
                preview,
                allow_tone_changes=True,
            )
        )
        self.assertEqual(
            scan.wait_for_changed_body(
                Frame(),
                previous,
                "top",
                "897",
                feature="tops",
                tile_preview=preview,
                timeout=0,
            ),
            changed,
        )

    def test_paired_tile_rejects_a_selected_body_with_a_stale_advertised_sibling(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632&bottom=632"

        class StalePairedFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=632&bottom=old"
                if script == scan.JS_PICKER_COUNT:
                    return 0
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan, "select_outfit_tile", return_value=True):
            options, errors = scan.scan_outfit_options(
                StalePairedFrame(),
                [{"id": "632", "preview": preview}],
                "top",
                base,
                feature="outfits",
                selected_body_timeout=0,
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertIn("confirmed selected body preview", errors[0]["error"])

    def test_paired_tile_keeps_every_advertised_garment_param(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632&bottom=632"
        selected = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=632&bottom=632&footwear=old"

        class PairedFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return selected
                if script == scan.JS_PICKER_COUNT:
                    return 0
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan, "select_outfit_tile", return_value=True):
            options, errors = scan.scan_outfit_options(
                PairedFrame(),
                [{"id": "632", "preview": preview}],
                "top",
                base,
                feature="outfits",
                picker_timeout=0,
            )

        self.assertEqual(errors, [])
        self.assertEqual(options[0]["render"]["params"], {"top": "632", "bottom": "632"})

    def test_selected_body_preview_supplies_paired_garment_params(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        tile_preview = "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?bottom=632"
        selected_body = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "gender=1&top=632&bottom=632"
        )

        class ColorlessFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return selected_body
                if script == scan.JS_PICKER_COUNT:
                    return 0
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan, "select_outfit_tile", return_value=True):
            options, errors = scan.scan_outfit_options(
                ColorlessFrame(),
                [{"id": "632", "preview": tile_preview}],
                "bottom",
                base,
                picker_timeout=0,
            )

        self.assertEqual(errors, [])
        self.assertEqual(options[0]["preview"], tile_preview)
        self.assertEqual(options[0]["render"]["params"], {"top": "632", "bottom": "632"})

    def test_top_scan_filters_a_bottom_left_by_a_previous_dress_scan(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        dress_body = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=632&bottom=632"
        top_body = (
            "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
            "gender=1&top=1062&top_tone1=16031775&bottom=632&bottom_tone1=12"
        )

        class ColorlessFrame:
            def __init__(self, body):
                self.body = body

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return self.body
                if script == scan.JS_PICKER_COUNT:
                    return 0
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan, "select_outfit_tile", return_value=True):
            dresses, dress_errors = scan.scan_outfit_options(
                ColorlessFrame(dress_body),
                [{"id": "632", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/one_piece?top=632&bottom=632"}],
                "bottom",
                base,
                feature="dresses",
                picker_timeout=0,
            )
            tops, top_errors = scan.scan_outfit_options(
                ColorlessFrame(top_body),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                base,
                feature="tops",
                picker_timeout=0,
            )

        self.assertEqual(dress_errors, [])
        self.assertEqual(dresses[0]["render"]["params"], {"top": "632", "bottom": "632"})
        self.assertEqual(top_errors, [])
        self.assertEqual(tops[0]["render"]["params"], {"top": "1062", "top_tone1": "16031775"})

    def test_unconfirmed_selected_body_keeps_the_item_unverified(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"

        class StaleBodyFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=old"
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan, "select_outfit_tile", return_value=True):
            options, errors = scan.scan_outfit_options(
                StaleBodyFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                base,
                feature="tops",
                selected_body_timeout=0,
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertIn("confirmed selected body preview", errors[0]["error"])

    def test_swatch_body_timeout_keeps_the_item_unverified(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        selected = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=1062"

        class StaticBodyFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return selected
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=(["#ec2020"], None)),
            mock.patch.object(scan, "active_picker_colour", return_value=None),
            mock.patch.object(scan, "click_picker_colour", return_value=True),
        ):
            options, errors = scan.scan_outfit_options(
                StaticBodyFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                base,
                feature="tops",
                swatch_timeout=0,
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertIn("relevant tone", errors[0]["error"])

    def test_cache_only_swatch_url_change_is_not_a_confirmed_tone_change(self):
        previous = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10&cacheable=1"
        cache_only = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10&cacheable=2"

        class CacheOnlyFrame:
            def __init__(self):
                self.bodies = iter([previous, cache_only])

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return next(self.bodies)
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=(["#ec2020"], None)),
            mock.patch.object(scan, "active_picker_colour", return_value=None),
            mock.patch.object(scan, "click_picker_colour", return_value=True),
        ):
            options, errors = scan.scan_outfit_options(
                CacheOnlyFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                previous,
                feature="tops",
                swatch_timeout=0,
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertNotIn("#ec2020", options[0]["render"].get("colour_variants", {}))
        self.assertIn("relevant tone", errors[0]["error"])

    def test_delayed_swatch_tone_change_is_confirmed_and_stored(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10"
        changed = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=20"

        class DelayedToneFrame:
            def __init__(self):
                self.bodies = iter([base, base, changed])

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return next(self.bodies)
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=(["#ec2020"], None)),
            mock.patch.object(scan, "active_picker_colour", return_value=None),
            mock.patch.object(scan, "click_picker_colour", return_value=True),
            mock.patch.object(scan.time, "sleep"),
        ):
            options, errors = scan.scan_outfit_options(
                DelayedToneFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                base,
                feature="tops",
                swatch_timeout=1,
            )

        self.assertEqual(errors, [])
        self.assertTrue(options[0]["colors_verified"])
        self.assertEqual(options[0]["render"]["colour_variants"]["#ec2020"], {"top_tone1": "20"})

    def test_active_singleton_without_tone_transition_stays_unverified(self):
        body = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10"

        class StaticFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return body
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=(["#ec2020"], None)),
            mock.patch.object(scan, "active_picker_colour", return_value="#ec2020"),
            mock.patch.object(scan, "click_picker_colour", return_value=True),
        ):
            options, errors = scan.scan_outfit_options(
                StaticFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                body,
                feature="tops",
                swatch_timeout=0,
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertNotIn("#ec2020", options[0]["render"].get("colour_variants", {}))
        self.assertIn("relevant tone", errors[0]["error"])

    def test_active_swatch_is_confirmed_after_transitioning_back_to_it(self):
        red = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10"
        blue = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=20"

        class RoundTripFrame:
            def __init__(self):
                self.bodies = iter([red, blue, red])

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return next(self.bodies)
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=(["#ec2020", "#010203"], None)),
            mock.patch.object(scan, "active_picker_colour", return_value="#ec2020"),
            mock.patch.object(scan, "click_picker_colour", return_value=True),
        ):
            options, errors = scan.scan_outfit_options(
                RoundTripFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                red,
                feature="tops",
                swatch_timeout=1,
            )

        self.assertEqual(errors, [])
        self.assertTrue(options[0]["colors_verified"])
        self.assertEqual(options[0]["render"]["colour_variants"]["#010203"], {"top_tone1": "20"})
        self.assertEqual(options[0]["render"]["colour_variants"]["#ec2020"], {"top_tone1": "10"})

    def test_body_and_picker_poll_until_the_editor_confirms_state(self):
        selected = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=1062"

        class DelayedFrame:
            def __init__(self):
                self.bodies = iter([
                    "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=old",
                    selected,
                ])
                self.picker_counts = iter([0, 1])

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return next(self.bodies)
                if script == scan.JS_PICKER_COUNT:
                    return next(self.picker_counts)
                raise AssertionError(f"unexpected browser script: {script}")

        frame = DelayedFrame()
        with mock.patch.object(scan.time, "sleep"):
            self.assertEqual(scan.wait_for_selected_body(frame, "top", "1062", timeout=1), selected)
            self.assertEqual(scan.wait_for_picker(frame, timeout=1), (True, None))

    def test_tile_selection_failure_keeps_the_item_unverified(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"
        with mock.patch.object(scan, "select_outfit_tile", return_value=False):
            options, errors = scan.scan_outfit_options(
                object(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                base,
                feature="tops",
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertIn("exact garment tile", errors[0]["error"])


class NavigationCompletenessTests(unittest.TestCase):
    def test_missing_active_category_marks_discovery_incomplete_and_blocks_write(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"

        class EarlyFrame:
            def __init__(self):
                self.categories = iter([{"id": "hair", "title": "Hair"}, None])

            def evaluate(self, script, *_args):
                if script == scan.JS_ACTIVE_CAT:
                    return next(self.categories)
                if script == scan.JS_FWD_HAS:
                    return True
                return None

        with mock.patch.object(
            scan,
            "collect_feature",
            return_value=(
                [
                    "https://preview.bitmoji.com/bm-preview/v3/avatar/hair?hair=1",
                    "https://preview.bitmoji.com/bm-preview/v3/avatar/hair?hair=2",
                ],
                [],
                None,
            ),
        ):
            features, order, errors, navigation_complete = scan.discover_features(EarlyFrame(), base)

        self.assertEqual(order, ["hair_style"])
        self.assertIn("hair_style", features)
        self.assertFalse(navigation_complete)
        self.assertIn("active category", errors[0]["error"])

        catalog = {"generated_at": "now", "source": "test", "features": features}
        report = scan.build_audit_report(catalog, errors, navigation_complete)
        self.assertFalse(report["complete"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bitmoji_catalog.json"
            target.write_text('{"existing": true}', encoding="utf-8")
            with (
                mock.patch.object(scan, "CATALOG_PATH", target),
                mock.patch.object(scan, "scan_live_catalog", return_value=(catalog, report)),
            ):
                self.assertEqual(scan.main(["profile-123", "--write"]), 1)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"existing": True})

    def test_repeated_blank_and_iteration_limit_navigation_exits_are_write_blocked(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"

        class CategoryFrame:
            def __init__(self, categories):
                self.categories = iter(categories)

            def evaluate(self, script, *_args):
                if script == scan.JS_ACTIVE_CAT:
                    return next(self.categories)
                if script == scan.JS_FWD_HAS:
                    return True
                return None

        imgs = [
            "https://preview.bitmoji.com/bm-preview/v3/avatar/hair?hair=1",
            "https://preview.bitmoji.com/bm-preview/v3/avatar/hair?hair=2",
        ]
        cases = (
            ([{"id": "hair", "title": "Hair"}, {"id": "hair", "title": "Hair"}], "repeated active category"),
            ([{"id": "", "title": ""}], "no id or title"),
        )
        with mock.patch.object(scan, "collect_feature", return_value=(imgs, [], None)):
            for categories, expected_error in cases:
                features, _order, errors, complete = scan.discover_features(CategoryFrame(categories), base)
                report = scan.build_audit_report({"generated_at": "now", "source": "test", "features": features}, errors, complete)
                self.assertFalse(complete)
                self.assertIn(expected_error, errors[0]["error"])
                self.assertFalse(scan.can_write_catalog(scan.parse_args(["profile", "--write"]), report["complete"]))

            with mock.patch.object(scan, "CATEGORY_SCAN_LIMIT", 1):
                features, _order, errors, complete = scan.discover_features(
                    CategoryFrame([{"id": "hair", "title": "Hair"}]), base,
                )
            report = scan.build_audit_report({"generated_at": "now", "source": "test", "features": features}, errors, complete)
            self.assertFalse(complete)
            self.assertIn("iteration limit", errors[0]["error"])
            self.assertFalse(scan.can_write_catalog(scan.parse_args(["profile", "--write"]), report["complete"]))


class EnumerationCompletenessTests(unittest.TestCase):
    def _assert_write_is_blocked(self, error):
        catalog = {"generated_at": "now", "source": "test", "features": {}}
        report = scan.build_audit_report(catalog, [error], navigation_complete=True)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bitmoji_catalog.json"
            target.write_text('{"existing": true}', encoding="utf-8")
            with (
                mock.patch.object(scan, "CATALOG_PATH", target),
                mock.patch.object(scan, "scan_live_catalog", return_value=(catalog, report)),
            ):
                self.assertEqual(scan.main(["profile", "--write"]), 1)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"existing": True})

    def test_feature_scroll_cap_is_explicit_and_write_blocked(self):
        class EndlessFeatureFrame:
            def __init__(self):
                self.position = 0

            def evaluate(self, script, *_args):
                if script == scan.JS_SCROLL_TO:
                    self.position += 140
                    return {"h": 1000, "t": self.position - 140, "ch": 1}
                if script == scan.JS_COLLECT:
                    return {"imgs": [], "fills": []}
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "FEATURE_SCROLL_LIMIT", 1),
            mock.patch.object(scan, "FEATURE_SWEEP_LIMIT", 1),
            mock.patch.object(scan.time, "sleep"),
        ):
            _imgs, _fills, error = scan.collect_feature(EndlessFeatureFrame())

        self.assertIn("feature scroll cap", error)
        self._assert_write_is_blocked({"feature": "hair_style", "error": error})

    def test_feature_scroll_stall_is_explicit_and_write_blocked(self):
        class StalledFeatureFrame:
            def __init__(self):
                self.scroll_calls = 0

            def evaluate(self, script, *_args):
                if script == scan.JS_SCROLL_TO:
                    self.scroll_calls += 1
                    return {"h": 1000, "t": 0, "ch": 100}
                if script == scan.JS_COLLECT:
                    return {"imgs": [], "fills": []}
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan.time, "sleep"):
            _imgs, _fills, error = scan.collect_feature(StalledFeatureFrame())

        self.assertIn("did not progress", error)
        self._assert_write_is_blocked({"feature": "hair_style", "error": error})

    def test_picker_scroll_cap_is_explicit_and_makes_item_partial(self):
        class EndlessPickerFrame:
            def __init__(self):
                self.position = 0

            def evaluate(self, script, *_args):
                if script == scan.JS_PICKER_COLORS:
                    return []
                if script == scan.JS_PICKER_SCROLL:
                    position = self.position
                    self.position += 160
                    return {"h": 1000, "t": position, "ch": 1}
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "PICKER_SCROLL_LIMIT", 1),
            mock.patch.object(scan.time, "sleep"),
        ):
            _colors, error = scan.picker_colours(EndlessPickerFrame())

        self.assertIn("picker scroll cap", error)

        selected = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062"

        class SelectedFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return selected
                if script == scan.JS_PICKER_COUNT:
                    return 1
                raise AssertionError(f"unexpected browser script: {script}")

        with (
            mock.patch.object(scan, "select_outfit_tile", return_value=True),
            mock.patch.object(scan, "picker_colours", return_value=([], error)),
        ):
            options, errors = scan.scan_outfit_options(
                SelectedFrame(),
                [{"id": "1062", "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/top?top=1062"}],
                "top",
                selected,
                feature="tops",
            )

        self.assertFalse(options[0]["colors_verified"])
        self.assertIn("picker scroll cap", errors[0]["error"])
        self._assert_write_is_blocked({"feature": "tops", "error": errors[0]["error"]})

    def test_picker_scroll_stall_is_explicit_and_makes_item_partial(self):
        class StalledPickerFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_PICKER_COLORS:
                    return []
                if script == scan.JS_PICKER_SCROLL:
                    return {"h": 1000, "t": 0, "ch": 100}
                raise AssertionError(f"unexpected browser script: {script}")

        with mock.patch.object(scan.time, "sleep"):
            _colors, error = scan.picker_colours(StalledPickerFrame())

        self.assertIn("did not progress", error)


    def test_recognized_empty_category_is_explicit_and_write_blocked(self):
        base = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1"

        class EmptyCategoryFrame:
            def evaluate(self, script, *_args):
                if script == scan.JS_ACTIVE_CAT:
                    return {"id": "hair", "title": "Hair"}
                if script == scan.JS_FWD_HAS:
                    return False
                return None

        with mock.patch.object(scan, "collect_feature", return_value=([], [], None)):
            features, _order, errors, complete = scan.discover_features(EmptyCategoryFrame(), base)

        self.assertEqual(features, {})
        self.assertTrue(complete)
        self.assertIn("no discovered options", errors[0]["error"])
        self._assert_write_is_blocked(errors[0])


class PickerScopeTests(unittest.TestCase):
    def test_wait_for_picker_palette_waits_for_selected_body_tones(self):
        selected = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=897&top_tone1=3171228"

        class Frame:
            def __init__(self):
                self.reads = 0

            def evaluate(self, script, *_args):
                if script == scan.JS_PICKER_SCROLL:
                    return {"h": 100, "t": 0, "ch": 50}
                if script == scan.JS_PICKER_COLORS:
                    self.reads += 1
                    return ["#111111"] if self.reads == 1 else ["#30639c"]
                raise AssertionError(f"unexpected browser script: {script}")

        frame = Frame()
        with mock.patch.object(scan.time, "sleep"):
            ready, error = scan.wait_for_picker_palette(frame, selected, "tops", timeout=1)

        self.assertTrue(ready)
        self.assertIsNone(error)
        self.assertEqual(frame.reads, 2)

    def test_picker_colours_resets_virtual_scroll_before_first_grab(self):
        class Frame:
            def __init__(self):
                self.reset_settled = False

            def evaluate(self, script, *_args):
                if script == scan.JS_PICKER_COLORS:
                    return ["#222222"] if self.reset_settled else ["#111111"]
                if script == scan.JS_PICKER_SCROLL:
                    return {"h": 0, "t": 0, "ch": 0}
                raise AssertionError(f"unexpected browser script: {script}")

        frame = Frame()

        def mark_reset_settled(_seconds):
            frame.reset_settled = True

        with mock.patch.object(scan.time, "sleep", side_effect=mark_reset_settled):
            colors, error = scan.picker_colours(frame)

        self.assertIsNone(error)
        self.assertEqual(colors, ["#222222"])

    def test_click_picker_colour_waits_after_resetting_virtual_scroll(self):
        class Frame:
            def __init__(self):
                self.slept_after_reset = False

            def evaluate(self, script, *_args):
                if script == scan.JS_PICKER_SCROLL:
                    return {"h": 0, "t": 0, "ch": 0}
                if script == scan.JS_CLICK_PICKER_COLOR:
                    return self.slept_after_reset
                raise AssertionError(f"unexpected browser script: {script}")

        frame = Frame()

        def mark_virtualized_dom_settled(_seconds):
            frame.slept_after_reset = True

        with mock.patch.object(scan.time, "sleep", side_effect=mark_virtualized_dom_settled):
            self.assertTrue(scan.click_picker_colour(frame, "#f5eaea"))

    def test_visible_picker_root_counts_enumerates_and_clicks_all_its_swatches(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for picker helper DOM regression")
        helpers = json.dumps({
            "count": scan.JS_PICKER_COUNT,
            "scroll": scan.JS_PICKER_SCROLL,
            "colors": scan.JS_PICKER_COLORS,
            "click": scan.JS_CLICK_PICKER_COLOR,
        })
        harness = f"""
const helpers = {helpers};
class Element {{
	  constructor(className, style, parent=null) {{
	    this.className=className; this.style=style; this.parentElement=parent;
	    this.children=[]; this.scrollHeight=0; this.clientHeight=0; this.scrollTop=0; this.clicks=0; this.events=[];
	    if(parent) parent.children.push(this);
	  }}
  getBoundingClientRect() {{ return {{width:this.style.width, height:this.style.height}}; }}
  closest(_selector) {{
    let current=this;
    while(current) {{
      if(String(current.className).includes('colour') || String(current.className).includes('picker')) return current;
      current=current.parentElement;
    }}
    return null;
  }}
  querySelectorAll(selector) {{
    const out=[];
    const visit=(node)=>{{ for(const child of node.children) {{
      if(selector==='.colour-picker-option' && String(child.className).includes('colour-picker-option')) out.push(child);
      visit(child);
    }} }};
    visit(this); return out;
	  }}
	  click() {{ this.clicks += 1; }}
	  dispatchEvent(event) {{ this.events.push(event.type); return true; }}
	}}
	globalThis.MouseEvent = class MouseEvent {{
	  constructor(type, _init) {{ this.type = type; }}
	}};
	globalThis.window = globalThis;
	const hiddenRoot = new Element('hidden-picker', {{width:100,height:100,display:'none',visibility:'visible',backgroundColor:''}});
const hidden = new Element('colour-picker-option', {{width:20,height:20,display:'none',visibility:'visible',backgroundColor:'rgb(1, 2, 3)'}}, hiddenRoot);
const visibleRoot = new Element('colour-picker-panel', {{width:200,height:100,display:'block',visibility:'visible',backgroundColor:''}});
visibleRoot.scrollHeight=600; visibleRoot.clientHeight=100;
const red = new Element('colour-picker-option', {{width:20,height:20,display:'block',visibility:'visible',backgroundColor:'rgb(236, 32, 32)'}}, visibleRoot);
const blue = new Element('colour-picker-option', {{width:20,height:20,display:'block',visibility:'visible',backgroundColor:'rgb(1, 2, 3)'}}, visibleRoot);
const green = new Element('colour-picker-option', {{width:20,height:20,display:'block',visibility:'visible',backgroundColor:'rgb(4, 5, 6)'}}, visibleRoot);
globalThis.document = {{querySelectorAll: (selector) => selector==='.colour-picker-option' ? [hidden, red, blue, green] : []}};
globalThis.getComputedStyle = (element) => element.style;
const invoke = (source, ...args) => eval(`(${{source}})`)(...args);
const result = {{
  count: invoke(helpers.count),
  colors: invoke(helpers.colors),
	  scroll: invoke(helpers.scroll, 85),
	  clicked: invoke(helpers.click, '#010203'),
	  hiddenClicks: hidden.clicks,
	  blueClicks: blue.clicks,
	  blueEvents: blue.events,
	}};
console.log(JSON.stringify(result));
"""
        result = subprocess.run([node, "-e", harness], check=True, text=True, capture_output=True)
        observed = json.loads(result.stdout)

        self.assertEqual(observed["count"], 3)
        self.assertEqual(observed["colors"], ["#ec2020", "#010203", "#040506"])
        self.assertEqual(observed["scroll"], {"h": 600, "t": 85, "ch": 100})
        self.assertTrue(observed["clicked"])
        self.assertEqual(observed["hiddenClicks"], 0)
        self.assertEqual(observed["blueClicks"], 0)
        self.assertEqual(observed["blueEvents"], ["mousedown", "mouseup", "click"])


class OutfitTileSelectorTests(unittest.TestCase):
    def test_visible_garment_selector_clicks_mix_tiles_and_outfit_images(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for outfit tile DOM regression")
        selector = json.dumps(scan.JS_SELECT_OUTFIT_TILE)
        harness = f"""
const selector = {selector};
class Element {{
  constructor(tag, className, style, parent=null, attrs={{}}) {{
    this.tagName=tag; this.className=className; this.style=style; this.parentElement=parent;
    this.attrs=attrs; this.children=[]; this.clicks=0; this.src=attrs.src||'';
    if(parent) parent.children.push(this);
  }}
  getBoundingClientRect() {{ return {{width:this.style.width, height:this.style.height}}; }}
  getAttribute(name) {{ return this.attrs[name] ?? null; }}
  contains(node) {{
    let current=node;
    while(current) {{ if(current===this) return true; current=current.parentElement; }}
    return false;
  }}
  matchesOne(part) {{
    if(part.startsWith('.')) return String(this.className).split(/\\s+/).includes(part.slice(1));
    if(part.startsWith('[class*="')) return String(this.className).includes(part.slice(9, -2));
    return false;
  }}
  closest(selector) {{
    const parts=selector.split(',').map(part=>part.trim());
    let current=this;
    while(current) {{
      if(parts.some(part=>current.matchesOne(part))) return current;
      current=current.parentElement;
    }}
    return null;
  }}
  querySelectorAll(selector) {{
    const out=[];
    const visit=(node)=>{{ for(const child of node.children) {{
      if(selector.startsWith('img[') && child.tagName==='IMG' && String(child.src).includes('preview.bitmoji.com')) out.push(child);
      visit(child);
    }} }};
    visit(this);
    return out;
  }}
  click() {{ this.clicks += 1; }}
}}
const visible = {{width:50,height:50,display:'block',visibility:'visible'}};
const activeRoot = new Element('DIV', 'avatar-builder-category', visible);
const bareMatch = new Element('DIV', 'mix-and-match-container', visible, activeRoot);
const bareImg = new Element('IMG', 'trait', visible, bareMatch, {{src:'https://preview.bitmoji.com/avatar/top?top=1062'}});
const mismatch = new Element('DIV', 'mix-and-match-container', visible, activeRoot);
const mismatchImg = new Element('IMG', 'trait', visible, mismatch, {{src:'https://preview.bitmoji.com/avatar/top?top=999'}});
const unrelated = new Element('DIV', 'other-container', visible, activeRoot);
const unrelatedImg = new Element('IMG', 'trait', visible, unrelated, {{src:'https://preview.bitmoji.com/avatar/top?top=1062'}});
const outfitWrapper = new Element('DIV', 'outfit-container brand-outfit', visible, activeRoot);
const outfitImg = new Element('IMG', 'outfit', visible, outfitWrapper, {{src:'https://preview.bitmoji.com/avatar/outfit?bottom=537'}});
globalThis.document = {{
  baseURI: 'https://sdk.bitmoji.com/',
  querySelector: (query) => query==='[data-nyx-active]' ? activeRoot : null,
}};
globalThis.getComputedStyle = (element) => element.style;
const select = eval(`(${{selector}})`);
const selectedTop = select({{param:'top', optionId:'1062'}});
const selectedOutfit = select({{param:'bottom', optionId:'537'}});
console.log(JSON.stringify({{
  selectedTop,
  selectedOutfit,
  bare:bareMatch.clicks,
  bareImg:bareImg.clicks,
  mismatch:mismatch.clicks,
  unrelated:unrelated.clicks,
  unrelatedImg:unrelatedImg.clicks,
  outfitWrapper:outfitWrapper.clicks,
  outfitImg:outfitImg.clicks,
}}));
"""
        result = subprocess.run([node, "-e", harness], check=True, text=True, capture_output=True)
        observed = json.loads(result.stdout)

        self.assertTrue(observed["selectedTop"])
        self.assertTrue(observed["selectedOutfit"])
        self.assertEqual(observed["bare"], 1)
        self.assertEqual(observed["bareImg"], 0)
        self.assertEqual(observed["mismatch"], 0)
        self.assertEqual(observed["unrelated"], 0)
        self.assertEqual(observed["unrelatedImg"], 0)
        self.assertEqual(observed["outfitWrapper"], 1)
        self.assertEqual(observed["outfitImg"], 1)


class AuditBoundaryTests(unittest.TestCase):
    def _complete_required_garments(self):
        return {
            feature: {
                "type": "outfit",
                "options": [{
                    "id": feature,
                    "colors_verified": True,
                    "render": {"params": {feature: "selected"}},
                }],
            }
            for feature in scan.REQUIRED_GARMENT_FEATURES
        }

    def test_report_target_cannot_alias_catalog_before_a_scan_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "data" / "bitmoji_catalog.json"
            equivalent_report = catalog.parent / "." / catalog.name
            with (
                mock.patch.object(scan, "CATALOG_PATH", catalog),
                mock.patch.object(scan, "scan_live_catalog") as scan_live_catalog,
            ):
                with self.assertRaises(SystemExit):
                    scan.main(["profile", "--report", str(equivalent_report)])
            scan_live_catalog.assert_not_called()

    def test_missing_required_garment_feature_blocks_an_otherwise_complete_audit(self):
        features = self._complete_required_garments()
        del features["outerwear"]
        catalog = {"generated_at": "now", "source": "test", "features": features}
        report = scan.build_audit_report(catalog, [], navigation_complete=True)

        self.assertFalse(report["complete"])
        self.assertIn("outerwear", report["garment_errors"][0]["error"])
        self.assertFalse(scan.can_write_catalog(scan.parse_args(["profile", "--write"]), report["complete"]))

    def test_required_garment_with_color_type_blocks_write(self):
        features = self._complete_required_garments()
        features["tops"]["type"] = "color"
        report = scan.build_audit_report(
            {"generated_at": "now", "source": "test", "features": features},
            [],
            navigation_complete=True,
        )

        self.assertFalse(report["complete"])
        self.assertTrue(any("tops must have type 'outfit'" in item["error"] for item in report["garment_errors"]))
        self.assertFalse(scan.can_write_catalog(scan.parse_args(["profile", "--write"]), report["complete"]))

    def test_required_garment_with_unverified_item_blocks_write(self):
        features = self._complete_required_garments()
        features["bottoms"]["options"][0]["colors_verified"] = False
        report = scan.build_audit_report(
            {"generated_at": "now", "source": "test", "features": features},
            [],
            navigation_complete=True,
        )

        self.assertFalse(report["complete"])
        self.assertTrue(any("bottoms option bottoms has unverified colours" in item["error"] for item in report["garment_errors"]))

    def test_required_garment_with_missing_render_params_blocks_write(self):
        features = self._complete_required_garments()
        features["footwear"]["options"][0]["render"] = {"params": {}}
        report = scan.build_audit_report(
            {"generated_at": "now", "source": "test", "features": features},
            [],
            navigation_complete=True,
        )

        self.assertFalse(report["complete"])
        self.assertTrue(any("footwear option footwear has no valid render params" in item["error"] for item in report["garment_errors"]))

    def test_restore_reloads_and_requires_the_initial_body_state(self):
        initial = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062&top_tone1=10"

        class Frame:
            def __init__(self, body):
                self.body = body
                self.url = "https://sdk.bitmoji.com/web-builder"

            def evaluate(self, script, *_args):
                if script == scan.JS_BASE_AVATAR:
                    return self.body
                raise AssertionError(f"unexpected browser script: {script}")

        class Page:
            def __init__(self, frame):
                self.frames = [frame]
                self.reload_calls = 0

            def reload(self):
                self.reload_calls += 1

        good_page = Page(Frame(initial))
        restored, error = scan.restore_editor_state(good_page, initial, timeout=0)
        self.assertTrue(restored)
        self.assertIsNone(error)
        self.assertEqual(good_page.reload_calls, 1)

        class IframeRestorePage(Page):
            def evaluate(self, script, url):
                if script != scan.JS_RESET_BUILDER_FRAME:
                    raise AssertionError(f"unexpected page script: {script}")
                self.frames[0].url = url
                self.frames[0].body = ""
                return True

        iframe_page = IframeRestorePage(Frame("https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=999"))
        restored, error = scan.restore_editor_state(
            iframe_page,
            initial,
            timeout=0,
            base_frame_url="https://sdk.bitmoji.com/web-builder?top=1062&top_tone1=10",
        )
        self.assertTrue(restored)
        self.assertIsNone(error)
        self.assertEqual(iframe_page.reload_calls, 0)

        frame_url_page = Page(Frame(""))
        frame_url_page.frames[0].url = "https://sdk.bitmoji.com/web-builder?top=1062&top_tone1=10"
        restored, error = scan.restore_editor_state(frame_url_page, initial, timeout=0)
        self.assertTrue(restored)
        self.assertIsNone(error)
        self.assertEqual(frame_url_page.reload_calls, 1)

        bad_page = Page(Frame("https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=999"))
        restored, error = scan.restore_editor_state(bad_page, initial, timeout=0)
        self.assertFalse(restored)
        self.assertIn("did not return", error)
        report = scan.build_audit_report(
            {"generated_at": "now", "source": "test", "features": {key: {} for key in scan.REQUIRED_GARMENT_FEATURES}},
            [{"scope": "restoration", "error": error}],
            navigation_complete=True,
        )
        self.assertFalse(report["complete"])


class ScanLifecycleTests(unittest.TestCase):
    class Frame:
        url = "https://sdk.bitmoji.com/web-builder"

        def __init__(self, body):
            self.body = body

        def evaluate(self, script, *_args):
            if script == scan.JS_BASE_AVATAR:
                return self.body
            if script == scan.JS_CLICK_BACK:
                return None
            raise AssertionError(f"unexpected browser script: {script}")

    class Page:
        def __init__(self, frame):
            self.frames = [frame]
            self.reload_calls = 0

        def bring_to_front(self):
            return None

        def reload(self):
            self.reload_calls += 1

    def test_discovery_exception_still_restores_editor_and_reports_scan_error(self):
        body = "https://preview.bitmoji.com/bm-preview/v3/avatar/body?top=1062"
        page = self.Page(self.Frame(body))
        with (
            mock.patch.object(scan, "discover_features", side_effect=RuntimeError("CDP frame detached")),
            mock.patch.object(scan.time, "sleep"),
        ):
            _catalog, report = scan.scan_editor_page(page, "profile")

        self.assertEqual(page.reload_calls, 1)
        self.assertFalse(report["complete"])
        self.assertTrue(any("unexpected scan failure" in item["error"] for item in report["garment_errors"]))

    def test_missing_initial_body_still_attempts_reload(self):
        page = self.Page(self.Frame(""))

        restored, error = scan.restore_editor_state(page, "", timeout=0)

        self.assertEqual(page.reload_calls, 1)
        self.assertFalse(restored)
        self.assertIn("initial body preview", error)

    def test_waiting_for_editor_frame_does_not_pick_avatar_gender(self):
        class Button:
            def __init__(self):
                self.clicks = 0

            def click(self):
                self.clicks += 1

        class Page:
            def __init__(self, button):
                self.frames = []
                self.button = button

            def query_selector(self, selector):
                if selector == 'button[aria-label="Female Avatar"]':
                    return self.button
                return None

        button = Button()
        with (
            mock.patch.dict("sys.modules", {
                "playwright": mock.Mock(),
                "playwright.sync_api": mock.Mock(TimeoutError=TimeoutError),
            }),
            mock.patch.object(scan.time, "monotonic", side_effect=[0, 0, 1]),
            mock.patch.object(scan.time, "sleep"),
        ):
            frame = scan._ensure_editor_frame(Page(button), timeout=0.1)

        self.assertIsNone(frame)
        self.assertEqual(button.clicks, 0)


class CliAndWriteTests(unittest.TestCase):
    def test_default_cli_is_report_only_and_requires_a_profile(self):
        args = scan.parse_args(["profile-123"])
        self.assertFalse(args.write)
        self.assertFalse(scan.can_write_catalog(args, complete=True))

        write_args = scan.parse_args(["profile-123", "--write", "--report", "/tmp/report.json"])
        self.assertTrue(write_args.write)
        self.assertTrue(scan.can_write_catalog(write_args, complete=True))
        self.assertFalse(scan.can_write_catalog(write_args, complete=False))

        with self.assertRaises(SystemExit):
            scan.parse_args([])

    def test_atomic_json_write_replaces_the_target_with_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "report.json"
            scan.atomic_write_json(path, {"status": "complete", "errors": []})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"status": "complete", "errors": []})
            self.assertEqual(list(path.parent.glob(".report.json.*.tmp")), [])

    def test_adspower_cache_fallback_requires_validated_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cache = home / "Library/Application Support/adspower_global/cwd_global/source/cache"
            cache.mkdir(parents=True)
            (cache / "k1f2la8v-other").mkdir()
            (cache / "k1f2la8vx").mkdir()

            with mock.patch.object(scan.Path, "home", return_value=home):
                with self.assertRaises(SystemExit):
                    scan._ads_cache_dir("k1f2la8v")

            suffixed = cache / "k1f2la8v_i6wcie"
            suffixed.mkdir()
            with mock.patch.object(scan.Path, "home", return_value=home):
                self.assertEqual(scan._ads_cache_dir("k1f2la8v"), suffixed)

            (cache / "k1f2la8v_second").mkdir()
            with mock.patch.object(scan.Path, "home", return_value=home):
                with self.assertRaises(SystemExit):
                    scan._ads_cache_dir("k1f2la8v")

    def test_ws_endpoint_uses_validated_cache_when_local_api_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cache = home / "Library/Application Support/adspower_global/cwd_global/source/cache/k1f2la8v_i6wcie"
            cache.mkdir(parents=True)
            (cache / "DevToolsActivePort").write_text("1234\n/devtools/browser/abc\n", encoding="utf-8")

            with (
                mock.patch.object(scan.Path, "home", return_value=home),
                mock.patch.object(
                    scan,
                    "_get",
                    side_effect=scan.urllib.error.URLError(ConnectionRefusedError("refused")),
                ),
            ):
                self.assertEqual(
                    scan.ws_endpoint("k1f2la8v"),
                    "ws://127.0.0.1:1234/devtools/browser/abc",
                )


if __name__ == "__main__":
    unittest.main()
