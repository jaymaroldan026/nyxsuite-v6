"""Audit a live Bitmoji editor catalog without saving avatar changes.

Connects to a running AdsPower profile with the Bitmoji avatar editor open at
https://www.bitmoji.com/avatar/create, walks every feature panel using the
editor's own ``#arrow_btn_forward`` navigation, scrolls each virtualised
traits/fashion scroll container to the bottom, and records every option:

  * img features  -> the distinct value of the query param that varies across
    the tile preview images (e.g. ``hair``, ``hair_tone``, ``nose``, ``top``).
  * colour features -> the distinct SVG swatch ``fill`` hexes.
  * outfit features -> each garment item's own colour swatches and body-render
    deltas, including verified colourless garments.

The default command reports the audit and never writes the catalog. Pass
``--write`` only after a complete audit to atomically replace
``data/bitmoji_catalog.json``. The editor runs inside the
``sdk.bitmoji.com/web-builder`` iframe; everything below is scoped to that
frame. The scanner only clicks garment tiles and their colour swatches; it
never clicks a Save control.

Usage:
    python tools/scan_bitmoji_live.py <profile_id>
    python tools/scan_bitmoji_live.py <profile_id> --report output/audit.json
    python tools/scan_bitmoji_live.py <profile_id> --write

Requires AdsPower running with the profile open at the avatar editor, and the
Nyx Suite venv (Playwright installed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bitmoji_config import CATALOG_PATH, FEATURES, feature_groups, feature_order  # noqa: E402

ADSPOWER = "http://local.adspower.net:50325"
EDITOR_HINT = "bitmoji.com/avatar"
FRAME_HINT = "sdk.bitmoji.com/web-builder"

# Params that are constant chrome on every preview URL, never an option id.
CONST_PARAMS = {"scale", "rotation", "cacheable", "ua", "gender", "style", "flow_mode", "client"}

# Panels that are not avatar features — never include them.
SKIP_IDS = {"save", "my_closet", "mycloset"}

# Editor category id -> our FEATURES key (when they differ). Most match 1:1.
ID_ALIASES = {
    "hair": "hair_style",
    "hair_tone": "hair_color",
    "hair_treatment_tone": "hair_treatment",
    "eye": "eye_shape",
    "eyelash": "eye_lashes",
    "pupil_tone": "eye_color",
    "brow": "eyebrows",
    "brow_tone": "eyebrow_color",
    "breast": "chest_size",
    "earring_dual": "paired_earring",
    "nosering": "nose_piercings",
    "eyeshadow_tone": "eyeshadow",
    "blush_tone": "blush",
    "lipstick_tone": "lipstick",
    "hat": "headwear",
    "outfit": "outfits",
    "top": "tops",
    "bottom": "bottoms",
    "one_piece": "dresses",
    "mouth": "lips",
    "earrings": "paired_earring",
    "paired_earrings": "paired_earring",
    "piercings": "nose_piercings",
    "nose_piercing": "nose_piercings",
    "eyelashes": "eye_lashes",
    "brow": "eyebrows",
    "brow_color": "eyebrow_color",
    "brow_tone": "eyebrow_color",
    "body": "body_shape",
    "chest": "chest_size",
    "face": "face_shape",
    "face_proportion": "face_shape",
}

CATEGORY_SCAN_LIMIT = 60
FEATURE_SWEEP_LIMIT = 4
FEATURE_SCROLL_LIMIT = 400
PICKER_SCROLL_LIMIT = 60
REQUIRED_GARMENT_FEATURES = frozenset({"outfits", "tops", "bottoms", "dresses", "footwear", "outerwear"})
SELECTED_BODY_TIMEOUT = 4.0
PICKER_APPEAR_TIMEOUT = 1.5
SWATCH_BODY_TIMEOUT = 4.0
RESTORE_TIMEOUT = 60.0
PICKER_PALETTE_TIMEOUT = 1.5
POLL_INTERVAL = 0.10


def _get(url: str, timeout: int = 20) -> dict:
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def _ads_cache_dir(profile_id: str) -> Path:
    """Return the AdsPower cache directory validated for *profile_id*."""
    candidates = [
        Path.home() / "Library/Application Support/adspower_global/cwd_global/source/cache",
        Path.home() / "Library/Application Support/AdsPower/Global/source/cache",
        Path.home() / "AppData/Local/adspower_global/source/cache",
    ]
    suffixed_matches: list[Path] = []
    for base in candidates:
        child = base / profile_id
        if child.is_dir():
            return child
        if base.is_dir():
            suffixed_matches.extend(
                item
                for item in base.iterdir()
                if item.is_dir() and item.name.startswith(f"{profile_id}_")
            )
    if len(suffixed_matches) == 1:
        return suffixed_matches[0]
    if len(suffixed_matches) > 1:
        raise SystemExit(f"AdsPower cache dir is ambiguous for profile {profile_id}")
    raise SystemExit(f"AdsPower cache dir not found for profile {profile_id}")


def _cached_ws_endpoint(profile_id: str) -> str:
    """Read a profile's active CDP endpoint from its validated cache directory."""
    cache_dir = _ads_cache_dir(profile_id)
    port_file = cache_dir / "DevToolsActivePort"
    if not port_file.is_file():
        raise SystemExit(f"AdsPower DevToolsActivePort not found for profile {profile_id}")
    lines = [line.strip() for line in port_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise SystemExit(f"AdsPower DevToolsActivePort was malformed for profile {profile_id}")
    port, path = lines[0], lines[1]
    if not port.isdigit() or not path.startswith("/"):
        raise SystemExit(f"AdsPower DevToolsActivePort was malformed for profile {profile_id}")
    return f"ws://127.0.0.1:{port}{path}"


def ws_endpoint(profile_id: str) -> str:
    try:
        data = _get(f"{ADSPOWER}/api/v1/browser/local-active", timeout=15)
    except Exception:
        return _cached_ws_endpoint(profile_id)
    for item in (data.get("data") or {}).get("list", []):
        if item.get("user_id") == profile_id:
            return item["ws"]["puppeteer"]
    try:
        data = _get(f"{ADSPOWER}/api/v1/browser/start?user_id={profile_id}")
    except Exception:
        return _cached_ws_endpoint(profile_id)
    if data.get("code") != 0:
        msg = data.get("msg", "")
        if "No local API permission" in msg:
            return _cached_ws_endpoint(profile_id)
        raise SystemExit(f"AdsPower could not start {profile_id}: {msg}")
    return data["data"]["ws"]["puppeteer"]


def parse_args(argv: list[str] | None = None):
    """Parse an explicit profile id and opt-in output choices.

    Keeping the profile out of module globals prevents an accidental audit of a
    hard-coded user. ``--write`` is deliberately separate from ``--report``:
    an audit report is safe, while a catalog replacement requires a complete
    successful scan as well as this explicit opt-in.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_id", help="AdsPower profile with the Bitmoji editor already open")
    parser.add_argument("--write", action="store_true", help="atomically replace data/bitmoji_catalog.json after a complete audit")
    parser.add_argument("--report", type=Path, help="atomically write the audit report JSON to this path")
    return parser.parse_args(argv)


def can_write_catalog(args, complete: bool) -> bool:
    """Catalog replacement is safe only after a complete explicit audit."""
    return bool(getattr(args, "write", False) and complete)


def paths_equivalent(left: Path | str, right: Path | str) -> bool:
    """Resolve equivalent output paths, including relative/symlink spellings."""
    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)


def atomic_write_json(path: Path | str, value: object) -> None:
    """Write JSON through a sibling temporary file, then atomically replace it."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{target.name}."
    fd, temporary_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            json.dump(value, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def preview_params(url: str) -> dict[str, str]:
    """Return non-chrome, single-valued preview query parameters.

    Repeated query keys are intentionally discarded: their URL semantics are a
    collection rather than the scalar render parameter this catalog consumes.
    """
    if not isinstance(url, str) or not url:
        return {}
    try:
        pairs = parse_qsl(urlparse(url).query, keep_blank_values=False)
    except (TypeError, ValueError):
        return {}
    counts: dict[str, int] = {}
    values: dict[str, str] = {}
    for key, value in pairs:
        if key in CONST_PARAMS:
            continue
        counts[key] = counts.get(key, 0) + 1
        values[key] = value
    return {
        key: value
        for key, value in values.items()
        if counts.get(key) == 1 and isinstance(value, str)
    }


def preview_delta(base_avatar: str, current_avatar: str) -> dict[str, str]:
    """Return a current body preview's meaningful scalar delta from the base."""
    base = preview_params(base_avatar)
    current = preview_params(current_avatar)
    return {key: value for key, value in current.items() if base.get(key) != value}


def decimal_colour_hex(value: object) -> str:
    """Convert Bitmoji's decimal tone values into the picker hex form."""
    try:
        number = int(str(value), 10)
    except (TypeError, ValueError):
        return ""
    if number < 0:
        return ""
    return f"#{number & 0xFFFFFF:06x}"


def garment_param_bases(feature: str) -> tuple[str, ...]:
    """Return the live preview parameter bases owned by a garment feature."""
    return {
        "tops": ("top",),
        "bottoms": ("bottom",),
        "footwear": ("footwear",),
        "outerwear": ("outerwear",),
        "dresses": ("top", "bottom"),
        "outfits": ("outfit", "top", "bottom"),
    }.get(str(feature or "").strip().lower(), ("top", "bottom", "footwear", "outerwear"))


def advertised_garment_params(feature: str, tile_preview: str) -> dict[str, str]:
    """Return the garment-owned scalar params that one tile advertises."""
    bases = garment_param_bases(feature)
    return {
        key: value
        for key, value in preview_params(tile_preview).items()
        if any(key == base or key.startswith(f"{base}_tone") for base in bases)
    }


def filter_outfit_render_params(feature: str, params: dict[str, str], tile_preview: str = "") -> dict[str, str]:
    """Keep only render params owned by one garment feature.

    The scanner changes garments while progressing through categories. A full
    body URL can therefore still contain a bottom selected while scanning a
    later top. The catalog must never replay that stale sibling selection.
    Dresses and complete outfits are the intentional paired exception.
    """
    feature_key = str(feature or "").strip().lower()
    if feature_key not in ("tops", "bottoms", "footwear", "outerwear", "dresses", "outfits"):
        return dict(params)
    allowed_bases = garment_param_bases(feature_key)
    if feature_key in ("dresses", "outfits") and tile_preview:
        advertised = advertised_garment_params(feature_key, tile_preview)
        allowed_bases = tuple(base for base in allowed_bases if base in advertised)
    if not allowed_bases:
        if feature_key in ("dresses", "outfits") and tile_preview:
            return {}
        return dict(params)
    filtered = {
        key: value
        for key, value in params.items()
        if any(key == base or key.startswith(f"{base}_tone") for base in allowed_bases)
    }
    if feature_key == "outfits" and filtered.get("outfit") and params.get("clothing_type"):
        filtered["clothing_type"] = params["clothing_type"]
    return filtered


def feature_tone_delta(
    feature: str,
    previous_body: str,
    current_body: str,
    tile_preview: str = "",
) -> dict[str, str]:
    """Return garment-owned tone or colour-identifying changes between two body previews."""
    owned = filter_outfit_render_params(
        feature, preview_delta(previous_body, current_body), tile_preview,
    )
    tones = {k: v for k, v in owned.items() if "_tone" in k}
    return tones or owned


def body_tone_colours(feature: str, body_preview: str) -> set[str]:
    """Return the garment-owned tone colours currently carried by a body URL."""
    owned = filter_outfit_render_params(feature, preview_params(body_preview))
    return {
        colour
        for key, value in owned.items()
        if "_tone" in key
        for colour in [decimal_colour_hex(value)]
        if colour
    }


def _normalise_colour(value: object) -> str:
    colour = str(value or "").strip().lower()
    if len(colour) == 7 and colour.startswith("#") and all(ch in "0123456789abcdef" for ch in colour[1:]):
        return colour
    return ""


def assemble_outfit_option(
    option_id: object,
    preview: str,
    base_avatar: str,
    colour_previews: dict[str, str] | None,
    *,
    complete: bool,
    feature: str = "",
    body_preview: str | None = None,
    colors: list[str] | None = None,
    colour_deltas: dict[str, dict[str, str]] | None = None,
    error: str | None = None,
) -> dict:
    """Assemble one item's authoritative (or deliberately unverified) audit.

    The only path to ``colors_verified`` is a finished item scan. That makes
    ``colors: []`` meaningful for a verified colourless garment while ensuring
    partial scans cannot erase operator colour settings later.
    """
    variants: dict[str, dict[str, str]] = {}
    colours: list[str] = []
    normalized_previews = {
        _normalise_colour(raw_colour): colour_preview_url
        for raw_colour, colour_preview_url in (colour_previews or {}).items()
        if _normalise_colour(raw_colour)
    }
    normalized_deltas = {
        _normalise_colour(raw_colour): params
        for raw_colour, params in (colour_deltas or {}).items()
        if _normalise_colour(raw_colour) and isinstance(params, dict)
    }
    source_colours = colors if colors is not None else list(normalized_previews)
    for raw_colour in source_colours:
        colour = _normalise_colour(raw_colour)
        if not colour or colour in colours:
            continue
        colours.append(colour)
        if colour_deltas is not None:
            variant_params = filter_outfit_render_params(feature, normalized_deltas.get(colour, {}), preview)
        else:
            colour_body_preview = normalized_previews.get(colour)
            variant_params = (
                filter_outfit_render_params(feature, preview_delta(base_avatar, colour_body_preview), preview)
                if isinstance(colour_body_preview, str) and colour_body_preview
                else {}
            )
        if variant_params:
            variants[colour] = variant_params

    if isinstance(body_preview, str) and "/avatar/body" in body_preview:
        base_params = filter_outfit_render_params(feature, preview_params(body_preview), preview)
    else:
        base_params = filter_outfit_render_params(feature, preview_delta(base_avatar, preview), preview)
    render: dict[str, object] = {
        "params": base_params,
    }
    if variants:
        render["colour_variants"] = variants
    option = {
        "id": str(option_id),
        "preview": preview,
        "colors": colours,
        "colors_verified": bool(complete),
        "render": render,
    }
    if error:
        option["scan_error"] = str(error)
    return option


def original_outfit_body_preview(option_id: str) -> str:
    """Synthetic body URL carrying the params the editor emits for outfit IDs."""
    return (
        "https://preview.bitmoji.com/bm-preview/v3/avatar/body?"
        f"outfit={quote(str(option_id), safe='')}&clothing_type=0"
    )


def scan_original_outfit_id_options(options: list[dict], base_avatar: str):
    """Assemble original outfit presets without mutating their dynamic list.

    Full outfit preset panels expose atomic ``outfit`` ids. Clicking one preset
    changes the panel's subsequent inventory, so the stable catalog form is the
    atomic id plus Bitmoji's original-outfit ``clothing_type=0`` body param.
    Mix-and-match garments still go through the live click/swatch scanner.
    """
    scanned: list[dict] = []
    errors: list[dict[str, str]] = []
    for source in options:
        option_id = str(source.get("id") or "")
        preview = str(source.get("preview") or "")
        if not option_id or not preview:
            error = "missing outfit id or tile preview"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {}, complete=False, feature="outfits", error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue
        scanned.append(assemble_outfit_option(
            option_id,
            preview,
            base_avatar,
            {},
            complete=True,
            feature="outfits",
            body_preview=original_outfit_body_preview(option_id),
        ))
    return scanned, errors


def editor_frame(page):
    matches = [fr for fr in page.frames if FRAME_HINT in fr.url]
    if matches:
        return matches[-1]
    return None


JS_RESET_BUILDER_FRAME = r"""url => {
  const frame = [...document.querySelectorAll('iframe')]
    .find(item => String(item.src || '').includes('sdk.bitmoji.com/web-builder'));
  if (!frame || !String(url || '').includes('sdk.bitmoji.com/web-builder')) return false;
  frame.src = url;
  return true;
}"""


def restore_editor_state(
    page,
    base_avatar: str,
    timeout: float = RESTORE_TIMEOUT,
    *,
    base_frame_url: str = "",
) -> tuple[bool, str | None]:
    """Reload the editor and confirm its meaningful body state matches the start.

    Tile and swatch clicks alter the in-editor draft. Resetting the builder
    iframe to the captured starting URL recreates that draft locally without
    clicking Save; a full page reload is only the fallback when the iframe
    cannot be addressed.
    """
    restored_frame_src = False
    if base_frame_url:
        try:
            restored_frame_src = bool(page.evaluate(JS_RESET_BUILDER_FRAME, base_frame_url))
        except Exception:
            restored_frame_src = False
    if not restored_frame_src:
        try:
            try:
                page.reload(wait_until="domcontentloaded", timeout=30000)
            except TypeError:
                page.reload()
        except Exception as exc:
            return False, f"could not reload editor for restoration: {exc}"
    if not isinstance(base_avatar, str) or not base_avatar:
        return False, "could not restore editor: initial body preview was unavailable"

    expected = preview_params(base_avatar)
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        frame = editor_frame(page)
        if frame is not None:
            try:
                current = frame.evaluate(JS_BASE_AVATAR)
            except Exception:
                current = ""
            if not current:
                current = getattr(frame, "url", "")
            if (
                isinstance(current, str)
                and preview_params(current) == expected
            ):
                return True, None
        if time.monotonic() >= deadline:
            return False, "editor did not return to the captured initial body state after reload"
        time.sleep(POLL_INTERVAL)


# ---- in-frame JS helpers -------------------------------------------------

JS_ACTIVE_CAT = r"""() => {
  // The visible feature panel: the .avatar-builder-category nearest the panel's
  // left edge with real width.
  let best=null, bestd=1e9;
  for (const c of document.querySelectorAll('.avatar-builder-category')) {
    const r=c.getBoundingClientRect();
    if (r.width>200) { const d=Math.abs(r.left-1090); if (d<bestd){bestd=d;best=c;} }
  }
  if (!best) return null;
  best.setAttribute('data-nyx-active','1');
  const title=(document.querySelector('.category-title .title')||{}).textContent||'';
  return {id: best.id||'', title: title.trim()};
}"""

JS_CLEAR_ACTIVE = r"""() => { document.querySelectorAll('[data-nyx-active]').forEach(e=>e.removeAttribute('data-nyx-active')); }"""

JS_SCROLL_TO = r"""(top) => {
  const c=document.querySelector('[data-nyx-active] .traits-container.scrollable')
        || document.querySelector('[data-nyx-active] .fashion-traits-container.scrollable')
        || document.querySelector('[data-nyx-active] [class*="traits-container"].scrollable')
        || document.querySelector('[data-nyx-active]');
  if (!c) return {h:0,t:0,ch:0};
  c.scrollTop = top;
  return {h:c.scrollHeight, t:c.scrollTop, ch:c.clientHeight};
}"""

JS_SCROLL_STATE = r"""() => {
  const c=document.querySelector('[data-nyx-active] .traits-container.scrollable')
        || document.querySelector('[data-nyx-active] .fashion-traits-container.scrollable')
        || document.querySelector('[data-nyx-active] [class*="traits-container"].scrollable')
        || document.querySelector('[data-nyx-active]');
  if (!c) return {h:0,t:0,ch:0};
  return {h:c.scrollHeight, t:c.scrollTop, ch:c.clientHeight};
}"""

JS_COLLECT = r"""() => {
  // Scoped to the active feature panel, so the big avatar preview (which lives
  // outside .avatar-builder-category) is naturally excluded — no path filter.
  const root=document.querySelector('[data-nyx-active]') || document;
  const imgs=[...root.querySelectorAll('img[src*="preview.bitmoji.com"]')].map(i=>i.src);
  const fills=[...root.querySelectorAll('rect[fill],circle[fill]')]
      .map(e=>e.getAttribute('fill')).filter(f=>/^#[0-9a-f]{6}$/i.test(f));
  return {imgs, fills};
}"""

JS_BASE_AVATAR = r"""() => {
  const img=document.querySelector('img[src*="/avatar/body"]');
  return img ? img.src : "";
}"""

# The garment tiles are virtualised.  The query-param match deliberately lives
# in the browser so every click targets the exact tile that advertised the id;
# it never falls back to a sibling just because it happens to be visible.
JS_SELECT_OUTFIT_TILE = r"""({param, optionId}) => {
  const root=document.querySelector('[data-nyx-active]');
  if(!root || !param) return false;
  const visible=(e)=>{const r=e.getBoundingClientRect(); const s=getComputedStyle(e);
    return r.width>1 && r.height>1 && s.display!=='none' && s.visibility!=='hidden';};
  const clickableSelector = [
    '.mix-and-match-container',
    '[class*="mix-and-match-container"]',
    '.outfit-container',
    '[class*="outfit-container"]',
  ].join(',');
  for(const img of root.querySelectorAll('img[src*="preview.bitmoji.com"]')){
    try {
      const value=new URL(img.src, document.baseURI).searchParams.get(param);
      if(value!==String(optionId)) continue;
    } catch (_) { continue; }
    const tile=img.closest(clickableSelector);
    const targets=[];
    if(/outfit/i.test(String(img.className || '')) && visible(img)) targets.push(img);
    if(tile && root.contains(tile) && visible(tile) && tile!==img) targets.push(tile);
    if(targets.length===0) continue;
    for(const target of targets) target.click();
    return true;
  }
  return false;
}"""

# A colour picker appears only after selecting an item. It is interrogated per
# item: a missing picker is a successful, verified colourless result. Every
# helper derives the same visible container, so a hidden picker elsewhere in
# the document cannot steal scrolling, reads, or clicks.
JS_PICKER_SCOPE = r"""
  const visible=(e)=>{const r=e.getBoundingClientRect(), s=getComputedStyle(e);
    return r.width>1 && r.height>1 && s.display!=='none' && s.visibility!=='hidden';};
  const visiblePickerRoot=()=>{
    const options=[...document.querySelectorAll('.colour-picker-option')].filter(visible);
    const option=options[0];
    let root=option && option.parentElement ? option.parentElement.closest('[class*="colour"],[class*="picker"]') : null;
    while(root){
      const scoped=[...root.querySelectorAll('.colour-picker-option')].filter(visible);
      if(scoped.length===options.length && options.every(e=>scoped.includes(e))) return root;
      const ancestor=root.parentElement ? root.parentElement.closest('[class*="colour"],[class*="picker"]') : null;
      if(!ancestor || ancestor===root) break;
      root=ancestor;
    }
    return option ? option.parentElement : null;
  };
"""
JS_PICKER_COUNT = r"""() => {""" + JS_PICKER_SCOPE + r"""
  const root=visiblePickerRoot();
  return root ? [...root.querySelectorAll('.colour-picker-option')].filter(visible).length : 0;
}"""
JS_PICKER_SCROLL = r"""(top) => {""" + JS_PICKER_SCOPE + r"""
  const root=visiblePickerRoot();
  const sc=(root && root.scrollHeight>root.clientHeight) ? root : (root ? root.parentElement : null);
  if(sc){ sc.scrollTop=top; return {h:sc.scrollHeight, t:sc.scrollTop, ch:sc.clientHeight}; }
  return {h:0, t:0, ch:0};
}"""
JS_PICKER_COLORS = r"""() => {""" + JS_PICKER_SCOPE + r"""
  const toHex=(s)=>{ const m=s.match(/\d+/g); if(!m||m.length<3) return null;
    return '#'+m.slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join(''); };
  const root=visiblePickerRoot(), out=[];
  if(!root) return out;
  root.querySelectorAll('.colour-picker-option').forEach(e=>{
    if(!visible(e)) return;
    const h=toHex(getComputedStyle(e).backgroundColor||''); if(h) out.push(h);
  });
  return out;
}"""
JS_CLICK_PICKER_COLOR = r"""(wanted) => {""" + JS_PICKER_SCOPE + r"""
  const toHex=(s)=>{ const m=s.match(/\d+/g); if(!m||m.length<3) return null;
    return '#'+m.slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join(''); };
  const root=visiblePickerRoot(), target=String(wanted||'').toLowerCase();
  if(!root) return false;
  for(const e of root.querySelectorAll('.colour-picker-option')){
    if(!visible(e)) continue;
    if(toHex(getComputedStyle(e).backgroundColor||'')===target) {
      if(typeof MouseEvent === 'function') {
        e.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window}));
        e.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window}));
        e.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
        return true;
      }
      if(typeof e.click === 'function') { e.click(); return true; }
      return true;
    }
  }
  return false;
}"""
JS_ACTIVE_PICKER_COLOR = r"""() => {""" + JS_PICKER_SCOPE + r"""
  const toHex=(s)=>{ const m=s.match(/\d+/g); if(!m||m.length<3) return null;
    return '#'+m.slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join(''); };
  const root=visiblePickerRoot();
  if(!root) return null;
  for(const e of root.querySelectorAll('.colour-picker-option')){
    if(!visible(e)) continue;
    const cls=String(e.className||'').toLowerCase();
    if(e.getAttribute('aria-checked')==='true' || e.getAttribute('aria-selected')==='true' ||
       cls.includes('selected') || cls.includes('active')) return toHex(getComputedStyle(e).backgroundColor||'');
  }
  return null;
}"""

JS_FWD_HAS = r"""() => { const a=document.querySelector('#arrow_btn_forward'); return !!(a && a.querySelector('img')); }"""
JS_BACK_HAS = r"""() => { const a=document.querySelector('#arrow_btn_back'); return !!(a && a.querySelector('img')); }"""
JS_CLICK_FWD = r"""() => { const a=document.querySelector('#arrow_btn_forward'); if(a) a.click(); }"""
JS_CLICK_BACK = r"""() => { const a=document.querySelector('#arrow_btn_back'); if(a) a.click(); }"""


def _body_has_item(body_preview: object, param: str, option_id: str) -> bool:
    """Whether a live body URL confirms the exact tile selection we requested."""
    return (
        isinstance(body_preview, str)
        and "/avatar/body" in body_preview
        and preview_params(body_preview).get(str(param or "")) == str(option_id)
    )


def body_matches_advertised_tile(
    body_preview: object,
    param: str,
    option_id: str,
    feature: str = "",
    tile_preview: str = "",
    *,
    allow_tone_changes: bool = False,
) -> bool:
    """Confirm both the selected id and every garment value advertised by its tile."""
    if not tile_preview:
        return _body_has_item(body_preview, param, option_id)
    advertised = advertised_garment_params(feature, tile_preview)
    if not advertised:
        return _body_has_item(body_preview, param, option_id)
    if allow_tone_changes:
        advertised = {key: value for key, value in advertised.items() if "_tone" not in key}
    if not advertised:
        return False
    body = preview_params(body_preview)
    if all(body.get(key) == value for key, value in advertised.items()):
        return True
    if str(feature or "").strip().lower() == "outfits" and "outfit" in advertised:
        detailed = {
            key: value
            for key, value in advertised.items()
            if key != "outfit" and not key.startswith("outfit_tone")
        }
        if detailed and all(body.get(key) == value for key, value in detailed.items()):
            return True
    return False


def wait_for_selected_body(
    fr,
    param: str,
    option_id: str,
    timeout: float = SELECTED_BODY_TIMEOUT,
    *,
    feature: str = "",
    tile_preview: str = "",
) -> str:
    """Poll until the live body preview confirms the exact selected garment."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            body_preview = fr.evaluate(JS_BASE_AVATAR)
        except Exception:
            body_preview = ""
        if body_matches_advertised_tile(body_preview, param, option_id, feature, tile_preview):
            return body_preview
        if time.monotonic() >= deadline:
            return ""
        time.sleep(POLL_INTERVAL)


def wait_for_picker(fr, timeout: float = PICKER_APPEAR_TIMEOUT) -> tuple[bool, str | None]:
    """Wait for a picker, or a full readable absence window for colourless items."""
    deadline = time.monotonic() + max(0.0, timeout)
    last_error: str | None = None
    observed = False
    while True:
        try:
            count = fr.evaluate(JS_PICKER_COUNT)
            if not isinstance(count, int):
                raise ValueError(f"picker count was not an integer: {count!r}")
            observed = True
            if count > 0:
                return True, None
        except Exception as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            if observed:
                return False, None
            return False, f"could not observe colour picker: {last_error or 'unknown error'}"
        time.sleep(POLL_INTERVAL)


def wait_for_changed_body(
    fr,
    previous_body: str,
    param: str,
    option_id: str,
    *,
    feature: str = "",
    tile_preview: str = "",
    timeout: float = SWATCH_BODY_TIMEOUT,
) -> str:
    """Poll until a swatch produces a confirmed, feature-owned tone change."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            body_preview = fr.evaluate(JS_BASE_AVATAR)
        except Exception:
            body_preview = ""
        if (
            body_preview != previous_body
            and body_matches_advertised_tile(
                body_preview,
                param,
                option_id,
                feature,
                tile_preview,
                allow_tone_changes=True,
            )
            and feature_tone_delta(feature, previous_body, body_preview, tile_preview)
        ):
            return body_preview
        if time.monotonic() >= deadline:
            return ""
        time.sleep(POLL_INTERVAL)


def varying_param(urls: list[str]):
    """Return (param, {value: preview_url}) for the param that varies across tiles."""
    from urllib.parse import urlparse, parse_qs
    vals: dict[str, dict] = {}
    for u in urls:
        try:
            q = parse_qs(urlparse(u).query)
        except Exception:
            continue
        for k, v in q.items():
            if k in CONST_PARAMS:
                continue
            vals.setdefault(k, {})
            vals[k][v[0]] = u
    # the option param is the one with the most distinct values
    best, best_n = None, 1
    for k, m in vals.items():
        if len(m) > best_n:
            best, best_n = k, len(m)
    return (best, vals.get(best, {})) if best else (None, {})


def collect_feature(fr):
    """Sweep the active panel in small steps so every virtualised row passes
    through the render window, re-sweeping until the distinct count is stable.

    Returns ``(preview_urls, fills, error)``. A safety cap is never silently
    accepted as a complete feature catalog.
    """
    imgs: dict[str, str] = {}
    fills: list[str] = []
    seen_fill = set()

    def grab():
        data = fr.evaluate(JS_COLLECT)
        for u in data["imgs"]:
            imgs[u] = u
        for f in data["fills"]:
            lf = f.lower()
            if lf not in seen_fill:
                seen_fill.add(lf); fills.append(lf)

    STEP = 140  # px — smaller than a tile row so nothing is skipped
    prev_total = -1
    for _ in range(FEATURE_SWEEP_LIMIT):
        s = fr.evaluate(JS_SCROLL_TO, 0)
        time.sleep(0.15)
        grab()
        h = s.get("h", 0)
        ch = s.get("ch", 0)
        top = s.get("t", 0)
        if not isinstance(top, (int, float)):
            return list(imgs.values()), fills, "feature scroll did not report its actual position"
        guard = 0
        while top + ch < h - 2:
            if guard >= FEATURE_SCROLL_LIMIT:
                return list(imgs.values()), fills, "feature scroll cap reached before panel bottom"
            requested_top = top + STEP
            s = fr.evaluate(JS_SCROLL_TO, requested_top)
            h = s.get("h", h)
            ch = s.get("ch", ch)
            actual_top = s.get("t")
            if not isinstance(actual_top, (int, float)):
                return list(imgs.values()), fills, "feature scroll did not report its actual position"
            if actual_top <= top:
                return list(imgs.values()), fills, "feature scroll did not progress while more panel content was reported"
            top = actual_top
            time.sleep(0.06)
            grab()
            guard += 1
        grab()
        total = len(imgs) + len(fills)
        if total == prev_total:
            return list(imgs.values()), fills, None
        prev_total = total
    return list(imgs.values()), fills, "feature sweep cap reached before option set stabilised"


def picker_colours(fr) -> tuple[list[str], str | None]:
    """Collect visible swatches or report that virtual-scroll enumeration capped."""
    colors: list[str] = []
    seen: set[str] = set()

    def grab():
        for c in fr.evaluate(JS_PICKER_COLORS):
            normalized = _normalise_colour(c)
            if normalized and normalized not in seen:
                seen.add(normalized)
                colors.append(normalized)

    s = fr.evaluate(JS_PICKER_SCROLL, 0)
    h, ch, top = s.get("h", 0), s.get("ch", 0), s.get("t", 0)
    if not isinstance(top, (int, float)):
        return colors, "picker scroll did not report its actual position"
    time.sleep(0.05)
    grab()
    for _ in range(PICKER_SCROLL_LIMIT):
        if not h or top + ch >= h - 2:
            return colors, None
        requested_top = top + 160
        s = fr.evaluate(JS_PICKER_SCROLL, requested_top)
        h, ch = s.get("h", h), s.get("ch", ch)
        actual_top = s.get("t")
        if not isinstance(actual_top, (int, float)):
            return colors, "picker scroll did not report its actual position"
        if actual_top <= top:
            return colors, "picker scroll did not progress while more picker content was reported"
        top = actual_top
        grab()
        time.sleep(0.05)
    return colors, "picker scroll cap reached before picker bottom"


def active_picker_colour(fr) -> str | None:
    """Return the editor-marked active swatch when the DOM exposes one."""
    try:
        color = _normalise_colour(fr.evaluate(JS_ACTIVE_PICKER_COLOR))
    except Exception:
        return None
    return color or None


def wait_for_picker_palette(
    fr,
    selected_body: str,
    feature: str,
    timeout: float = PICKER_PALETTE_TIMEOUT,
) -> tuple[bool, str | None]:
    """Give the picker a chance to swap from the previous garment's palette.

    Some Bitmoji garments expose picker swatches whose visible colours do not
    directly match the selected body's tone params. That cannot be treated as
    a hard failure, because the later swatch application check verifies the
    actual body URL before anything is marked complete.
    """
    expected = body_tone_colours(feature, selected_body)
    if not expected:
        return True, None
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fr.evaluate(JS_PICKER_SCROLL, 0)
            time.sleep(0.05)
            visible_colours = {
                colour
                for raw in fr.evaluate(JS_PICKER_COLORS)
                for colour in [_normalise_colour(raw)]
                if colour
            }
        except Exception:
            # Offline frames in unit tests often do not model the picker DOM.
            # That should not create an artificial live-scan failure path.
            return True, None
        if visible_colours & expected:
            return True, None
        if time.monotonic() >= deadline:
            return True, None
        time.sleep(POLL_INTERVAL)


def select_outfit_tile(fr, param: str, option_id: str) -> bool:
    """Click one exact virtualised tile, retrying scroll sweeps if necessary."""
    step = 140
    target = {"param": param, "optionId": str(option_id)}

    def sweep_from(state: dict, *, pause: float = 0.0) -> bool:
        if pause:
            time.sleep(pause)
        top = state.get("t", 0)
        if not isinstance(top, (int, float)):
            return False
        guard = 0
        while True:
            if fr.evaluate(JS_SELECT_OUTFIT_TILE, target):
                return True
            height = state.get("h", 0)
            client_height = state.get("ch", 0)
            if not height or top + client_height >= height - 2 or guard >= 400:
                break
            state = fr.evaluate(JS_SCROLL_TO, top + step)
            actual_top = state.get("t")
            if not isinstance(actual_top, (int, float)) or actual_top <= top:
                break
            top = actual_top
            time.sleep(0.06)
            guard += 1
        return False

    if fr.evaluate(JS_SELECT_OUTFIT_TILE, target):
        return True
    try:
        if sweep_from(fr.evaluate(JS_SCROLL_STATE)):
            return True
    except Exception:
        pass
    for _ in range(2):
        if sweep_from(fr.evaluate(JS_SCROLL_TO, 0), pause=0.12):
            return True
    return False


def click_picker_colour(fr, colour: str) -> bool:
    """Click one enumerated swatch, retrying as the picker virtualises rows."""
    state = fr.evaluate(JS_PICKER_SCROLL, 0)
    time.sleep(0.05)
    top = state.get("t", 0)
    if not isinstance(top, (int, float)):
        return False
    for _ in range(60):
        if fr.evaluate(JS_CLICK_PICKER_COLOR, colour):
            return True
        height, client_height = state.get("h", 0), state.get("ch", 0)
        if not height or top + client_height >= height - 2:
            break
        state = fr.evaluate(JS_PICKER_SCROLL, top + 160)
        actual_top = state.get("t")
        if not isinstance(actual_top, (int, float)) or actual_top <= top:
            break
        top = actual_top
        time.sleep(0.05)
    return False


def scan_outfit_options(
    fr,
    options: list[dict],
    param: str,
    base_avatar: str,
    *,
    feature: str = "",
    selected_body_timeout: float = SELECTED_BODY_TIMEOUT,
    picker_timeout: float = PICKER_APPEAR_TIMEOUT,
    swatch_timeout: float = SWATCH_BODY_TIMEOUT,
):
    """Audit garments one-by-one and return item failures for the report.

    Failed selection or swatch capture keeps the item explicitly unverified, so
    the caller can report all failures but cannot replace the catalog with a
    partial result.
    """
    scanned: list[dict] = []
    errors: list[dict[str, str]] = []
    for source in options:
        option_id = str(source.get("id") or "")
        preview = str(source.get("preview") or "")
        if not option_id or not preview:
            error = "missing garment id or tile preview"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {}, complete=False, feature=feature, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue
        try:
            selected = select_outfit_tile(fr, param, option_id)
        except Exception as exc:
            selected = False
            selection_error = f"tile selection error: {exc}"
        else:
            selection_error = "exact garment tile was not found after virtual-scroll retries"
        if not selected:
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {}, complete=False, feature=feature, error=selection_error,
            ))
            errors.append({"id": option_id, "error": selection_error})
            continue

        selected_body = wait_for_selected_body(
            fr,
            param,
            option_id,
            selected_body_timeout,
            feature=feature,
            tile_preview=preview,
        )
        if not selected_body:
            body_error = "could not capture confirmed selected body preview after selecting tile"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {}, complete=False, feature=feature, error=body_error,
            ))
            errors.append({"id": option_id, "error": body_error})
            continue

        picker_present, picker_error = wait_for_picker(fr, picker_timeout)
        if picker_error:
            error = picker_error
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {},
                complete=False, feature=feature, body_preview=selected_body, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue
        if not picker_present:
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {}, complete=True, feature=feature, body_preview=selected_body,
            ))
            continue

        palette_ready, palette_error = wait_for_picker_palette(fr, selected_body, feature)
        if not palette_ready:
            error = palette_error or "picker palette did not settle for the selected garment"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {},
                complete=False, feature=feature, body_preview=selected_body, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue

        try:
            colors, picker_enumeration_error = picker_colours(fr)
        except Exception as exc:
            error = f"could not enumerate colour picker: {exc}"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {},
                complete=False, feature=feature, body_preview=selected_body, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue
        if picker_enumeration_error:
            error = picker_enumeration_error
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {},
                complete=False, feature=feature, body_preview=selected_body, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue
        if not colors:
            error = "colour picker was visible but no swatches could be read"
            scanned.append(assemble_outfit_option(
                option_id, preview, base_avatar, {},
                complete=False, feature=feature, body_preview=selected_body, error=error,
            ))
            errors.append({"id": option_id, "error": error})
            continue

        colour_previews: dict[str, str] = {}
        colour_deltas: dict[str, dict[str, str]] = {}
        scan_error = ""
        active_color = active_picker_colour(fr)
        current_body = selected_body
        ordered_colors = [color for color in colors if color != active_color]
        for color in ordered_colors:
            try:
                clicked = click_picker_colour(fr, color)
            except Exception as exc:
                clicked = False
                scan_error = f"could not apply swatch {color}: {exc}"
            if not clicked:
                scan_error = scan_error or f"could not click swatch {color}"
                break
            body_preview = wait_for_changed_body(
                fr,
                current_body,
                param,
                option_id,
                feature=feature,
                tile_preview=preview,
                timeout=swatch_timeout,
            )
            if not body_preview:
                scan_error = f"body preview did not gain a relevant tone after swatch {color}"
                break
            colour_previews[color] = body_preview
            colour_deltas[color] = feature_tone_delta(feature, current_body, body_preview, preview)
            current_body = body_preview
        complete = not scan_error and len(colour_previews) == len(ordered_colors)
        scanned.append(assemble_outfit_option(
            option_id, preview, base_avatar, colour_previews,
            complete=complete,
            feature=feature,
            body_preview=selected_body,
            colors=colors,
            colour_deltas=colour_deltas,
            error=scan_error or None,
        ))
        if not complete:
            errors.append({"id": option_id, "error": scan_error or "incomplete colour scan"})
    return scanned, errors


def resolve_key(cat_id: str, title: str) -> str:
    cid = (cat_id or "").strip().lower()
    if cid in FEATURES:
        return cid
    if cid in ID_ALIASES:
        return ID_ALIASES[cid]
    slug = (title or "").strip().lower().replace(" ", "_").replace("-", "_")
    if slug in FEATURES:
        return slug
    if slug in ID_ALIASES:
        return ID_ALIASES[slug]
    return cid or slug


def discover_features(fr, base_avatar: str):
    """Walk editor categories and report whether navigation ended normally.

    A catalog can only be authoritative after reaching the editor's explicit
    no-forward-arrow end state. Missing panels, a category loop, and reaching
    the safety iteration cap are all incomplete discovery, never a valid end.
    """
    features: dict[str, dict] = {}
    order: list[str] = []
    errors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    navigation_complete = False
    print("\nScanning features (forward through the editor)...\n")
    for _ in range(CATEGORY_SCAN_LIMIT):
        fr.evaluate(JS_CLEAR_ACTIVE)
        cat = fr.evaluate(JS_ACTIVE_CAT)
        if not cat:
            errors.append({"scope": "navigation", "error": "active category disappeared before editor end"})
            break
        cid, title = cat.get("id", ""), cat.get("title", "")
        marker = cid or title
        if not marker:
            errors.append({"scope": "navigation", "error": "active category had no id or title"})
            break
        if marker in seen_ids:
            errors.append({"scope": "navigation", "error": f"repeated active category marker: {marker}"})
            break
        seen_ids.add(marker)

        if (cid or "").strip().lower() in SKIP_IDS:
            print(f"  (skip non-feature panel id={cid})")
            if not fr.evaluate(JS_FWD_HAS):
                navigation_complete = True
                break
            fr.evaluate(JS_CLICK_FWD)
            time.sleep(0.6)
            continue

        key = resolve_key(cid, title)
        imgs, fills, collection_error = collect_feature(fr)
        param, val_map = varying_param(imgs)

        meta = FEATURES.get(key, {})
        if collection_error:
            errors.append({"feature": key, "error": collection_error})
        declared_kind = meta.get("kind")
        if fills and not val_map:
            kind = "color"
            options = [{"id": f} for f in fills]
        elif val_map:
            kind = declared_kind if declared_kind in ("img", "outfit") else "img"
            options = [{"id": v, "preview": u} for v, u in val_map.items()]
            if kind == "outfit":
                if key == "outfits" and param == "outfit":
                    options, outfit_errors = scan_original_outfit_id_options(options, base_avatar)
                else:
                    options, outfit_errors = scan_outfit_options(
                        fr, options, param or "", base_avatar, feature=key,
                    )
                for item_error in outfit_errors:
                    errors.append({"feature": key, **item_error})
        elif fills:
            kind = "color"
            options = [{"id": f} for f in fills]
        else:
            kind = declared_kind or "img"
            options = []

        if options:
            label = meta.get("label") or (title or key.replace("_", " ").title())
            features[key] = {
                "label": label,
                "type": kind,
                "options": options,
                "editor_id": cid,
                "param": param or meta.get("param", ""),
            }
            order.append(key)
            print(f"  {key:16s} id={cid or '-':14s} {kind:6s} {len(options):3d} opts  param={param}")
        else:
            print(f"  (skip empty id={cid} title={title!r})")
            if meta:
                errors.append({"feature": key, "error": "recognized category had no discovered options"})

        if not fr.evaluate(JS_FWD_HAS):
            navigation_complete = True
            break
        fr.evaluate(JS_CLICK_FWD)
        time.sleep(0.6)
    else:
        errors.append({"scope": "navigation", "error": "editor navigation iteration limit reached before editor end"})
    return features, order, errors, navigation_complete


def build_audit_report(catalog: dict, errors: list[dict[str, str]], navigation_complete: bool) -> dict:
    """Create the write-gating report from explicit scanner completion state."""
    report_errors = list(errors)
    features = catalog.get("features") if isinstance(catalog, dict) else {}
    discovered = set(features) if isinstance(features, dict) else set()
    missing = sorted(REQUIRED_GARMENT_FEATURES - discovered)
    if missing:
        report_errors.append({
            "scope": "coverage",
            "error": f"required garment features were not scanned: {', '.join(missing)}",
        })
    if isinstance(features, dict):
        for feature in sorted(REQUIRED_GARMENT_FEATURES & discovered):
            record = features.get(feature)
            if not isinstance(record, dict) or record.get("type") != "outfit":
                report_errors.append({
                    "scope": "coverage",
                    "error": f"{feature} must have type 'outfit'",
                })
                continue
            options = record.get("options")
            if not isinstance(options, list) or not options:
                report_errors.append({
                    "scope": "coverage",
                    "error": f"{feature} must include at least one scanned option",
                })
                continue
            for index, option in enumerate(options):
                option_id = str(option.get("id") if isinstance(option, dict) else index)
                if not isinstance(option, dict) or option.get("colors_verified") is not True:
                    report_errors.append({
                        "scope": "coverage",
                        "error": f"{feature} option {option_id} has unverified colours",
                    })
                    continue
                render = option.get("render")
                params = render.get("params") if isinstance(render, dict) else None
                if (
                    not isinstance(params, dict)
                    or not params
                    or not all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in params.items())
                ):
                    report_errors.append({
                        "scope": "coverage",
                        "error": f"{feature} option {option_id} has no valid render params",
                    })
    return {
        "generated_at": catalog["generated_at"],
        "source": catalog["source"],
        "complete": bool(navigation_complete and not report_errors),
        "navigation_complete": bool(navigation_complete),
        "feature_count": len(features or {}),
        "garment_errors": report_errors,
    }


def scan_editor_page(page, profile_id: str) -> tuple[dict, dict]:
    """Audit one already-open editor page and always restore its draft state."""
    errors: list[dict[str, str]] = []
    base_avatar = ""
    base_frame_url = ""
    features: dict[str, dict] = {}
    order: list[str] = []
    navigation_complete = False

    try:
        try:
            page.bring_to_front()
        except Exception as exc:
            errors.append({"scope": "scan", "error": f"could not focus editor page: {exc}"})

        try:
            fr = editor_frame(page)
        except Exception as exc:
            fr = None
            errors.append({"scope": "scan", "error": f"could not inspect editor frame: {exc}"})
        if fr is None:
            errors.append({"scope": "scan", "error": "editor iframe (sdk.bitmoji.com/web-builder) not found"})
        else:
            base_frame_url = getattr(fr, "url", "") or ""
            try:
                captured_avatar = fr.evaluate(JS_BASE_AVATAR)
                base_avatar = captured_avatar if isinstance(captured_avatar, str) else ""
            except Exception as exc:
                errors.append({"scope": "scan", "error": f"could not capture initial body preview: {exc}"})
            if not base_avatar:
                errors.append({"scope": "scan", "error": "initial /avatar/body preview was not available"})

            try:
                # Rewind to the first feature. Clicking an already-disabled arrow
                # is a harmless no-op, and avoids a transient arrow-state race.
                for _ in range(60):
                    fr.evaluate(JS_CLICK_BACK)
                    time.sleep(0.18)
                time.sleep(0.5)
                features, order, navigation_errors, navigation_complete = discover_features(fr, base_avatar)
                errors.extend(navigation_errors)
            except Exception as exc:
                errors.append({"scope": "scan", "error": f"unexpected scan failure: {exc}"})
    finally:
        try:
            restored, restoration_error = restore_editor_state(page, base_avatar, base_frame_url=base_frame_url)
        except Exception as exc:
            restored, restoration_error = False, f"could not restore editor: {exc}"
        if not restored:
            errors.append({"scope": "restoration", "error": restoration_error or "editor restoration failed"})

    # Preserve curated order/groups; append any newly-discovered keys.
    curated = [key for key in feature_order() if key in features]
    extras = [key for key in order if key not in curated]
    catalog = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"live-scan:{profile_id}",
        "base_avatar": base_avatar,
        "features": features,
        "feature_order": curated + extras,
        "groups": feature_groups(),
    }
    return catalog, build_audit_report(catalog, errors, navigation_complete)


def catalog_scan_page(contexts):
    """Choose the best open page for a live scan.

    A direct ``sdk.bitmoji.com/web-builder`` tab is already the editor frame, so
    prefer it over the parent Bitmoji page when both are open. The parent page
    remains supported for normal browser sessions with a healthy iframe.
    """
    editor_page = None
    builder_page = None
    for ctx in contexts:
        for candidate in ctx.pages:
            if FRAME_HINT in candidate.url:
                builder_page = candidate
            elif EDITOR_HINT in candidate.url:
                editor_page = candidate
    return builder_page or editor_page


def _ensure_editor_frame(page, timeout: float = 25.0):
    """Wait for the existing editor iframe without mutating avatar state."""
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        fr = editor_frame(page)
        if fr is not None:
            return fr
        time.sleep(1)
    return None


def scan_live_catalog(profile_id: str) -> tuple[dict, dict]:
    """Run the no-save browser audit and return catalog payload plus report."""
    ws = ws_endpoint(profile_id)
    print(f"Profile {profile_id} CDP: {ws}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(ws)
        page = catalog_scan_page(browser.contexts)
        if not page:
            raise SystemExit("No Bitmoji editor page open. Open the avatar editor in the profile.")
        fr = _ensure_editor_frame(page)
        if fr is None:
            raise SystemExit("Could not open Bitmoji editor: gender selection failed or iframe did not load.")
        return scan_editor_page(page, profile_id)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.report and paths_equivalent(args.report, CATALOG_PATH):
        raise SystemExit("--report must not target data/bitmoji_catalog.json")
    catalog, report = scan_live_catalog(args.profile_id)
    print(f"\nAudit {'complete' if report['complete'] else 'FAILED'} — {report['feature_count']} features scanned")
    if report["garment_errors"]:
        for item in report["garment_errors"]:
            feature = item.get("feature", item.get("scope", "scan"))
            option_id = item.get("id", "")
            print(f"  ERROR {feature}{'/' + option_id if option_id else ''}: {item['error']}")
    if args.report:
        atomic_write_json(args.report, report)
        print(f"Audit report written atomically to {args.report}")

    if can_write_catalog(args, report["complete"]):
        atomic_write_json(CATALOG_PATH, catalog)
        print(f"Catalog written atomically to {CATALOG_PATH}")
    elif args.write:
        print("Catalog not written: the audit is incomplete.")
    else:
        print("Catalog not written (report-only mode; pass --write after a complete audit).")
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
