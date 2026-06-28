"""Build ``data/bitmoji_catalog.json`` from saved Bitmoji editor MHTML panels.

The Bitmoji avatar editor renders each feature as a grid of option tiles. An
option is identified either by a query param in its preview image URL
(``hair=1307``, ``nose=1494``) or, for colour features (skin tone, eye colour,
makeup), by an SVG swatch ``fill``. ``core.bitmoji_config.FEATURES`` says, per
feature, which file to read and how to read it.

Note: the editor's grids are virtualised, so a saved panel only contains the
options that were in the DOM when saved. Scroll a panel fully before saving to
capture more. Re-run this script whenever you refresh the captures.

Usage:
    python tools/build_bitmoji_catalog.py ["C:/Users/you/Documents/Bitmoji"]
"""

from __future__ import annotations

import email
import html as html_lib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bitmoji_config import CATALOG_PATH, FEATURES, feature_order as get_feature_order, feature_groups as get_feature_groups  # noqa: E402

DEFAULT_SOURCE = Path.home() / "Documents" / "Bitmoji"
PREVIEW_HOST = "preview.bitmoji.com"

# Some capture folders name a panel slightly differently from FEATURES[...]["file"].
# Map a feature's expected file stem to extra stems to accept (all lower-case).
FILE_ALIASES: dict[str, list[str]] = {
    "outerwear": ["outwear"],
}


def load_main_html(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes())
    parts = [
        p.get_payload(decode=True).decode("utf-8", "replace")
        for p in msg.walk()
        if p.get_content_type() == "text/html" and p.get_payload(decode=True)
    ]
    return max(parts, key=len) if parts else ""


def extract_img_options(html: str, path_seg: str, param: str) -> list[dict]:
    """Distinct ``param`` values among preview imgs whose URL path is ``path_seg``."""
    urls = [html_lib.unescape(u) for u in re.findall(
        r'src="(https://[^"]*?' + re.escape(PREVIEW_HOST) + r'[^"]*)"', html)]
    seen: set[str] = set()
    options: list[dict] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.path.rsplit("/", 1)[-1] != path_seg:
            continue
        value = (parse_qs(parsed.query).get(param) or [""])[0]
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({"id": value, "preview": url})
    return options


def extract_base_avatar(html: str) -> str:
    """A full-body `/avatar/body?` preview URL — the template for the live
    dashboard preview (its facial params get overridden per selection)."""
    for url in re.findall(r'src="(https://[^"]*?' + re.escape(PREVIEW_HOST) + r'[^"]*)"', html):
        clean = html_lib.unescape(url)
        if urlparse(clean).path.rsplit("/", 1)[-1] == "body":
            return clean
    return ""


def extract_color_options(html: str, shape: str) -> list[dict]:
    fills = re.findall(r'<' + shape + r'[^>]*fill="(#[0-9a-fA-F]{6})"', html)
    seen: set[str] = set()
    options: list[dict] = []
    for hexval in fills:
        low = hexval.lower()
        if low in seen:
            continue
        seen.add(low)
        options.append({"id": low})
    return options


def extract_outfit_options(html: str, path_seg: str, param: str) -> list[dict]:
    """Extract outfit items with their available colors from the panel HTML.
    Returns options with ``{id, preview, colors: [colorId, ...]}``."""
    urls = [html_lib.unescape(u) for u in re.findall(
        r'src="(https://[^"]*?' + re.escape(PREVIEW_HOST) + r'[^"]*)"', html)]
    seen: set[str] = set()
    options: list[dict] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.path.rsplit("/", 1)[-1] != path_seg:
            continue
        value = (parse_qs(parsed.query).get(param) or [""])[0]
        if not value or value in seen:
            continue
        seen.add(value)
        options.append({"id": value, "preview": url, "colors": []})
    # Extract the panel's color swatches (one shared palette per outfit panel) and
    # attach it to every option, so the editor's per-garment colour picker and the
    # random-pool colour chips both have the full set to choose from.
    fills = re.findall(r'fill="(#[0-9a-fA-F]{6})"', html)
    palette: list[str] = []
    seen_fills: set[str] = set()
    for hexval in fills:
        low = hexval.lower()
        if low in seen_fills:
            continue
        seen_fills.add(low)
        palette.append(low)
    for opt in options:
        opt["colors"] = list(palette)
    return options


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    if not source.is_dir():
        print(f"Source folder not found: {source}")
        return 1

    # Merge into the existing catalog: only features whose panel file is present in
    # this source folder are (re)built; everything else is preserved. This lets you
    # refresh a subset (e.g. just the outfit panels) without re-capturing all 40+.
    existing = {}
    if CATALOG_PATH.exists():
        try:
            existing = json.loads(CATALOG_PATH.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = {}
    features: dict[str, dict] = dict(existing.get("features", {}) or {})
    base_avatar = str(existing.get("base_avatar") or "")

    # Case-insensitive lookup of panel files by stem.
    files = {p.stem.strip().lower(): p for p in source.glob("*.mhtml")}
    updated = 0
    for key, meta in FEATURES.items():
        stems = [meta["file"].lower(), *FILE_ALIASES.get(key, [])]
        panel = next((files[s] for s in stems if s in files), None)
        if not panel:
            if key not in features:
                print(f"  ? {key:16s} missing file '{meta['file']}.mhtml' — skipped")
            continue
        html = load_main_html(panel)
        new_base = extract_base_avatar(html)
        if new_base and not base_avatar:
            base_avatar = new_base
        if meta["kind"] == "img":
            options = extract_img_options(html, meta["path"], meta["param"])
        elif meta["kind"] == "outfit":
            options = extract_outfit_options(html, meta["path"], meta["param"])
            # Garment grids often don't include the colour-swatch panel. If this
            # capture has no swatches, keep the palette from the previous catalog
            # so the editor's outfit colour picker still works.
            if options and not any(o.get("colors") for o in options):
                prior = (features.get(key) or {}).get("options", [])
                palette: list[str] = []
                for o in prior:
                    for c in o.get("colors", []) or []:
                        if c not in palette:
                            palette.append(c)
                if palette:
                    for o in options:
                        o["colors"] = list(palette)
                    print(f"    ~ {key}: reused {len(palette)} colours from prior catalog")
        else:
            options = extract_color_options(html, meta["shape"])
        if not options:
            print(f"  ! {key:16s} no options found in {panel.name} — kept existing")
            continue
        prev = len((features.get(key) or {}).get("options", []))
        features[key] = {"label": meta["label"], "type": meta["kind"], "options": options}
        arrow = f"(was {prev})" if prev else ""
        print(f"  + {key:16s} {len(options):3d} options {arrow}  [{panel.name}]")
        updated += 1

    f_order = get_feature_order()
    f_groups = get_feature_groups()

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(source),
        "base_avatar": base_avatar,
        "features": features,
        "feature_order": f_order,
        "groups": f_groups,
    }, indent=2), encoding="utf-8")
    print(f"  base_avatar: {'present' if base_avatar else 'MISSING'}")
    print(f"\nWrote {CATALOG_PATH} — updated {updated} feature(s); {len(features)}/{len(FEATURES)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
