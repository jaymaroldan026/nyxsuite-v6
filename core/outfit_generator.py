import random
import hashlib
import time

from core.bitmoji_config import build_selector, catalog_option, load_catalog_raw, option_colors
from core.nyx_runtime_config import load_nyx_config
from snap_selectors.selectors import BITMOJI_SELECTORS

BLOCKED_TOP_IDS = {"924"}
BLOCKED_FOOTWEAR_IDS = {"712", "1019", "962", "722"}
CUTE_PRESET_STYLE = "cute_preset"

CASUAL_OUTFITS = {
    "tops": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=801')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=698')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=949')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=213')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=209')]]",
    ],
    "bottoms": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=356')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=818')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=788')]]",
    ],
    "dresses": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/one_piece?') and contains(@src,'top=903') and contains(@src,'bottom=903')]]",
    ],
    "footwear": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=292')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=470')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=969')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=920')]]",
    ],
}

SEXY_OUTFITS = {
    "tops": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=699')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=964')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=532')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=186')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=429')]]",
    ],
    "bottoms": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=948')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=922')]]",
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=287')]]",
    ],
    "dresses": [],
    "footwear": [
        "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=292')]]",
        {
            "selector": "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=245') and contains(@src,'footwear_tone1=1776156')]]",
            "preferred_color": {
                "background_contains": ["rgb(27, 26, 28)", "rgb(40, 39, 40)"]
            },
        },
    ],
}

CUTE_PRESET_SEPARATES = (
    ("pink_pleated", "801", "922", "292"),
    ("teal_black", "699", "147", "470"),
    ("corset_black", "964", "124", "245"),
    ("white_denim", "66", "384", "941"),
    ("blue_shorts", "477", "232", "760"),
    ("pink_cardigan", "949", "349", "935"),
    ("lavender_soft", "640", "149", "846"),
    ("peach_short", "532", "123", "920"),
    ("pink_black", "381", "147", "245"),
    ("teal_wrap", "186", "541", "468"),
    ("purple_pleat", "429", "922", "846"),
    ("lavender_black", "850", "147", "470"),
    ("white_red", "248", "398", "561"),
    ("red_black", "323", "124", "245"),
    ("black_pink", "278", "396", "935"),
    ("red_skirt", "475", "147", "290"),
    ("white_cutoff", "728", "384", "1009"),
    ("white_black", "757", "965", "598"),
    ("floral_white", "787", "922", "881"),
    ("peach_tan", "512", "123", "296"),
    ("pink_vest", "10000397", "232", "935"),
    ("cutie_denim", "10000097", "247", "743"),
    ("heart_pink", "10000095", "396", "935"),
    ("lips_black", "10000101", "147", "245"),
    ("olive_green", "853", "240", "192"),
    ("blue_white", "260", "349", "760"),
    ("purple_lace", "275", "147", "846"),
    ("peach_orange", "272", "151", "321"),
)

CUTE_PRESET_DRESSES = (
    ("pink_dress", "960", "292"),
    ("red_white_dress", "966", "245"),
    ("green_mini", "903", "192"),
    ("lavender_dress", "800", "846"),
    ("white_dress", "635", "1009"),
    ("gray_fitted", "631", "470"),
    ("black_dress", "630", "245"),
    ("red_dress", "632", "290"),
    ("white_short", "633", "844"),
    ("floral_dress", "702", "881"),
    ("navy_collar", "849", "603"),
    ("cream_skirt", "856", "1009"),
)

CUTE_PRESET_COLORWAYS = {
    "soft_cute": {
        "tops": ("#ff9aad", "#d3c6f2", "#b7d5e4", "#fafafa", "#f3d5a1"),
        "bottoms": ("#fafafa", "#b4dcea", "#ffccec", "#d3c6f2", "#f3d5a1"),
        "dresses": ("#e04e9f", "#c5c1e6", "#fafafa", "#ffccec", "#b7d5e4"),
        "footwear": ("#ecc1c4", "#fafafa", "#d3c6f2", "#fa7daa", "#b7d5e4"),
    },
    "seductive_classic": {
        "tops": ("#131313", "#da3041", "#e04e9f", "#fafafa", "#74418e"),
        "bottoms": ("#131313", "#1f1f1f", "#da3041", "#3073b7", "#687072"),
        "dresses": ("#131313", "#da3041", "#687072", "#e04e9f", "#13316a"),
        "footwear": ("#000000", "#181818", "#d03434", "#fafafa", "#a279e5"),
    },
    "pretty_casual": {
        "tops": ("#76c1b2", "#b7d5e4", "#f3d5a1", "#82a66a", "#ff9aad"),
        "bottoms": ("#b4dcea", "#879f84", "#d3b785", "#f3774d", "#fafafa"),
        "dresses": ("#82a66a", "#fafafa", "#c5c1e6", "#13316a", "#f3d5a1"),
        "footwear": ("#968a7e", "#fafafa", "#ecc1c4", "#ffe565", "#42ccaf"),
    },
}

_CUTE_COLOUR_MAX_DISTANCE = 90


def _filter_blocked_outfits(selectors, blocked_ids, trait_name):
    filtered = []

    for selector in selectors:
        selector_text = str(selector)
        if any(f"{trait_name}={blocked_id}" in selector_text for blocked_id in blocked_ids):
            continue
        filtered.append(selector)

    return filtered


def _merge_style_items(*groups):
    merged = []
    seen = set()

    for group in groups:
        for item in group:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    return merged


def _hex_rgb(value):
    text = str(value or "").strip().lower().lstrip("#")
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _colour_distance(left, right):
    return sum((left[i] - right[i]) ** 2 for i in range(3)) ** 0.5


def _preferred_palette_hex(feature, option_id, desired_hex, catalog):
    item = catalog_option(feature, option_id, catalog)
    if not item or item.get("colors_verified") is not True:
        return None
    desired_rgb = _hex_rgb(desired_hex)
    if desired_rgb is None:
        return None
    colors = option_colors(feature, option_id, catalog)
    ranked = []
    for color in colors:
        color_rgb = _hex_rgb(color)
        if color_rgb is None:
            continue
        ranked.append((_colour_distance(color_rgb, desired_rgb), str(color).strip()))
    if not ranked:
        return None
    distance, selected = min(ranked, key=lambda item: item[0])
    return selected if distance <= _CUTE_COLOUR_MAX_DISTANCE else None


def _cute_palette_target(colorway, feature, index):
    palette = CUTE_PRESET_COLORWAYS[colorway][feature]
    offsets = {"tops": 0, "bottoms": 2, "dresses": 1, "footwear": 3}
    return palette[(index + offsets.get(feature, 0)) % len(palette)]


def _cute_entry(feature, option_id, colorway, index, catalog):
    selector = build_selector(feature, option_id)
    if not selector:
        raise ValueError(f"Could not build Nyxmoji selector for {feature}={option_id}")
    entry = {"selector": selector}
    preferred_hex = _preferred_palette_hex(
        feature,
        option_id,
        _cute_palette_target(colorway, feature, index),
        catalog,
    )
    if preferred_hex:
        entry["preferred_color"] = {"hex": preferred_hex}
    return entry


def cute_preset_look_variants(catalog=None):
    """Return the 120 curated cute/seductive outfit variants.

    The preset is intentionally combination-based: garment IDs are curated as
    complete silhouettes, then expanded through three pretty palette families.
    A preferred colour is attached only when the live catalog verifies that the
    selected garment actually supports a close matching swatch.
    """
    source = load_catalog_raw() if catalog is None else catalog
    looks = []
    for colorway in CUTE_PRESET_COLORWAYS:
        for index, (name, top_id, bottom_id, shoe_id) in enumerate(CUTE_PRESET_SEPARATES):
            looks.append({
                "preset": CUTE_PRESET_STYLE,
                "name": f"{name}_{colorway}",
                "base_name": name,
                "colorway": colorway,
                "mode": "separates",
                "top": _cute_entry("tops", top_id, colorway, index, source),
                "bottom": _cute_entry("bottoms", bottom_id, colorway, index, source),
                "shoes": _cute_entry("footwear", shoe_id, colorway, index, source),
            })
        for index, (name, dress_id, shoe_id) in enumerate(CUTE_PRESET_DRESSES):
            looks.append({
                "preset": CUTE_PRESET_STYLE,
                "name": f"{name}_{colorway}",
                "base_name": name,
                "colorway": colorway,
                "mode": "dress",
                "dress": _cute_entry("dresses", dress_id, colorway, index, source),
                "shoes": _cute_entry("footwear", shoe_id, colorway, index, source),
            })
    return looks


def _generate_cute_preset_outfit(rng):
    looks = cute_preset_look_variants()
    if not looks:
        raise ValueError("Cute preset has no configured looks.")
    selected = rng.choice(looks)
    if selected["mode"] == "dress":
        dress_pool = [look["dress"] for look in looks if look["mode"] == "dress"]
        shoes_pool = [look["shoes"] for look in looks]
        return {
            "preset": CUTE_PRESET_STYLE,
            "name": selected["name"],
            "colorway": selected["colorway"],
            "mode": "dress",
            "dress": selected["dress"],
            "shoes": selected["shoes"],
            "dress_pool": dress_pool,
            "shoes_pool": shoes_pool,
        }

    top_pool = [look["top"] for look in looks if look["mode"] == "separates"]
    bottom_pool = [look["bottom"] for look in looks if look["mode"] == "separates"]
    shoes_pool = [look["shoes"] for look in looks]
    return {
        "preset": CUTE_PRESET_STYLE,
        "name": selected["name"],
        "colorway": selected["colorway"],
        "mode": "separates",
        "top": selected["top"],
        "bottom": selected["bottom"],
        "shoes": selected["shoes"],
        "top_pool": top_pool,
        "bottom_pool": bottom_pool,
        "shoes_pool": shoes_pool,
    }


def generate_outfit(profile_id, model="", outfit_seed=""):

    seed_source = str(outfit_seed).strip() or f"{profile_id}:{model}:{time.time_ns()}"
    seed = int(hashlib.md5(seed_source.encode()).hexdigest(), 16)
    rng = random.Random(seed)

    outfits = BITMOJI_SELECTORS["outfits"]
    runtime_config = load_nyx_config()
    outfit_style = str(runtime_config.get("outfit_style", "default")).strip().lower()

    if outfit_style == CUTE_PRESET_STYLE:
        return _generate_cute_preset_outfit(rng)

    if outfit_style == "default":
        available_tops = _filter_blocked_outfits(outfits["tops"], BLOCKED_TOP_IDS, "top")
        available_sandals = _filter_blocked_outfits(outfits["sandals"], BLOCKED_FOOTWEAR_IDS, "footwear")
        available_sneakers = _filter_blocked_outfits(outfits["sneakers"], BLOCKED_FOOTWEAR_IDS, "footwear")

        dress_probability = 0.20
        use_dress = rng.random() < dress_probability
        if use_dress:
            dress = rng.choice(outfits["dresses"])
            if not available_sandals:
                raise ValueError("No allowed sandals available after filtering blocked footwear IDs.")
            shoes = rng.choice(available_sandals)
            return {
                "mode": "dress",
                "dress": dress,
                "shoes": shoes,
                "dress_pool": list(outfits["dresses"]),
                "shoes_pool": list(available_sandals),
            }

        if not available_tops:
            raise ValueError("No allowed tops available after filtering blocked outfit IDs.")

        top = rng.choice(available_tops)
        bottom = rng.choice(outfits["bottoms"])
        if not available_sneakers:
            raise ValueError("No allowed sneakers available after filtering blocked footwear IDs.")

        shoes = rng.choice(available_sneakers)
        return {
            "mode": "separates",
            "top": top,
            "bottom": bottom,
            "shoes": shoes,
            "top_pool": list(available_tops),
            "bottom_pool": list(outfits["bottoms"]),
            "shoes_pool": list(available_sneakers),
        }

    if outfit_style == "casual":
        style_pool = CASUAL_OUTFITS
        dress_probability = 0.18
    elif outfit_style == "sexy":
        style_pool = SEXY_OUTFITS
        dress_probability = 0.0
    elif outfit_style == "mixed":
        style_pool = {
            "tops": _merge_style_items(CASUAL_OUTFITS["tops"], SEXY_OUTFITS["tops"]),
            "bottoms": _merge_style_items(CASUAL_OUTFITS["bottoms"], SEXY_OUTFITS["bottoms"]),
            "dresses": _merge_style_items(CASUAL_OUTFITS["dresses"], SEXY_OUTFITS["dresses"]),
            "footwear": _merge_style_items(CASUAL_OUTFITS["footwear"], SEXY_OUTFITS["footwear"]),
        }
        dress_probability = 0.10
    elif outfit_style == "no_dresses":
        style_pool = {
            "tops": _merge_style_items(CASUAL_OUTFITS["tops"], SEXY_OUTFITS["tops"]),
            "bottoms": _merge_style_items(CASUAL_OUTFITS["bottoms"], SEXY_OUTFITS["bottoms"]),
            "dresses": [],
            "footwear": _merge_style_items(CASUAL_OUTFITS["footwear"], SEXY_OUTFITS["footwear"]),
        }
        dress_probability = 0.0
    else:
        style_pool = CASUAL_OUTFITS
        dress_probability = 0.18

    available_tops = _filter_blocked_outfits(style_pool["tops"], BLOCKED_TOP_IDS, "top")
    available_dresses = style_pool["dresses"]
    available_footwear = _filter_blocked_outfits(style_pool["footwear"], BLOCKED_FOOTWEAR_IDS, "footwear")

    use_dress = bool(available_dresses) and rng.random() < dress_probability
    if use_dress:
        dress = rng.choice(available_dresses)
        if not available_footwear:
            raise ValueError("No allowed footwear available after filtering blocked footwear IDs.")
        shoes = rng.choice(available_footwear)
        return {
            "mode": "dress",
            "dress": dress,
            "shoes": shoes,
            "dress_pool": list(available_dresses),
            "shoes_pool": list(available_footwear),
        }

    if not available_tops:
        raise ValueError("No allowed tops available after filtering blocked outfit IDs.")

    top = rng.choice(available_tops)
    bottom = rng.choice(style_pool["bottoms"])
    if not available_footwear:
        raise ValueError("No allowed footwear available after filtering blocked footwear IDs.")

    shoes = rng.choice(available_footwear)

    return {
        "mode": "separates",
        "top": top,
        "bottom": bottom,
        "shoes": shoes,
        "top_pool": list(available_tops),
        "bottom_pool": list(style_pool["bottoms"]),
        "shoes_pool": list(available_footwear),
    }
