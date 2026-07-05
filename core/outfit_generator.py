import random
import hashlib
import time

from core.nyx_runtime_config import load_nyx_config
from snap_selectors.selectors import BITMOJI_SELECTORS

BLOCKED_TOP_IDS = {"924"}
BLOCKED_FOOTWEAR_IDS = {"712", "1019", "962", "722"}

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


def generate_outfit(profile_id, model="", outfit_seed=""):

    seed_source = str(outfit_seed).strip() or f"{profile_id}:{model}:{time.time_ns()}"
    seed = int(hashlib.md5(seed_source.encode()).hexdigest(), 16)
    rng = random.Random(seed)

    outfits = BITMOJI_SELECTORS["outfits"]
    runtime_config = load_nyx_config()
    outfit_style = str(runtime_config.get("outfit_style", "default")).strip().lower()

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
                "shoes": shoes
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
            "shoes": shoes
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
            "shoes": shoes
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
        "shoes": shoes
    }
