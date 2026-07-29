import copy
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import nyx_runtime_config, outfit_generator
from core.bitmoji_config import catalog_option, load_catalog_raw, option_colors


class CutePresetConfigTests(unittest.TestCase):
    def test_cute_preset_is_a_valid_outfit_style(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            config_path = data_dir / "nyx_config.json"
            with mock.patch.object(nyx_runtime_config, "DATA_DIR", data_dir), \
                 mock.patch.object(nyx_runtime_config, "CONFIG_PATH", config_path):
                saved = nyx_runtime_config.save_nyx_config({"outfit_style": "cute_preset"})
                self.assertEqual(saved["outfit_style"], "cute_preset")
                self.assertEqual(nyx_runtime_config.load_nyx_config()["outfit_style"], "cute_preset")


class CutePresetOutfitTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog_raw()

    def _selector_id(self, selector, param):
        match = re.search(rf"concat\('&{re.escape(param)}=', '([^']+)', '&'\)", str(selector))
        return match.group(1) if match else None

    def _assert_entry_is_catalog_backed(self, feature, entry):
        selector = entry["selector"]
        param = {
            "tops": "top",
            "bottoms": "bottom",
            "dresses": "bottom",
            "footwear": "footwear",
        }[feature]
        option_id = self._selector_id(selector, param)
        self.assertIsNotNone(option_id, selector)
        self.assertIsNotNone(catalog_option(feature, option_id, self.catalog), f"{feature} {option_id} missing")
        preferred = entry.get("preferred_color") or {}
        if preferred.get("hex"):
            colors = {color.lower() for color in option_colors(feature, option_id, self.catalog)}
            self.assertIn(preferred["hex"].lower(), colors)

    def test_cute_preset_exposes_120_catalog_backed_variants(self):
        looks = outfit_generator.cute_preset_look_variants()

        self.assertEqual(len(looks), 120)
        self.assertEqual(
            {look["colorway"] for look in looks},
            {"soft_cute", "seductive_classic", "pretty_casual"},
        )
        self.assertEqual(len({look["name"] for look in looks}), 120)

        for look in looks:
            with self.subTest(look=look["name"]):
                self.assertEqual(look["preset"], "cute_preset")
                if look["mode"] == "separates":
                    self._assert_entry_is_catalog_backed("tops", look["top"])
                    self._assert_entry_is_catalog_backed("bottoms", look["bottom"])
                    self._assert_entry_is_catalog_backed("footwear", look["shoes"])
                else:
                    self.assertEqual(look["mode"], "dress")
                    self._assert_entry_is_catalog_backed("dresses", look["dress"])
                    self._assert_entry_is_catalog_backed("footwear", look["shoes"])

    def test_cute_preset_avoids_blocked_item_ids(self):
        blocked = {"top": outfit_generator.BLOCKED_TOP_IDS, "footwear": outfit_generator.BLOCKED_FOOTWEAR_IDS}
        for look in outfit_generator.cute_preset_look_variants():
            for key in ("top", "bottom", "dress", "shoes"):
                entry = look.get(key)
                if not entry:
                    continue
                selector = entry["selector"]
                for param, ids in blocked.items():
                    for blocked_id in ids:
                        self.assertNotIn(f"&{param}=', '{blocked_id}', '&", selector)
                        self.assertNotIn(f"{param}={blocked_id}", selector)

    def test_generate_outfit_uses_cute_preset_deterministically_without_mutating_existing_presets(self):
        casual_before = copy.deepcopy(outfit_generator.CASUAL_OUTFITS)
        sexy_before = copy.deepcopy(outfit_generator.SEXY_OUTFITS)

        with mock.patch.object(outfit_generator, "load_nyx_config", return_value={"outfit_style": "cute_preset"}):
            first = outfit_generator.generate_outfit("profile-1", model="Willow", outfit_seed="seed-1")
            second = outfit_generator.generate_outfit("profile-1", model="Willow", outfit_seed="seed-1")

        self.assertEqual(first, second)
        self.assertEqual(first["preset"], "cute_preset")
        self.assertIn(first["mode"], {"separates", "dress"})
        self.assertEqual(outfit_generator.CASUAL_OUTFITS, casual_before)
        self.assertEqual(outfit_generator.SEXY_OUTFITS, sexy_before)


if __name__ == "__main__":
    unittest.main()
