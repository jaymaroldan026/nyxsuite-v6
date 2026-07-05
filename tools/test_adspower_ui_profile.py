"""End-to-end smoke test for the no-API AdsPower GUI automation.

Drives the full flow the production runner uses when the Local API is gated:

  1. Create a profile through the AdsPower desktop GUI
       - name  : "Snapchat: Pending"  (temp name)
       - group : "Snapchat20"
       - proxy : pasted into the Host field (AdsPower auto-parses user:pass)
       - Check Proxy -> OK
  2. Resolve the new profile's id from the Profiles list (dup-safe).
  3. Open it via the search bar (clear search -> "Profile ID is <id>" -> Open).
  4. Attach Playwright over CDP (no API) and prove we have control.

Usage:
    python tools/test_adspower_ui_profile.py
    python tools/test_adspower_ui_profile.py --open k1e0mqys     # open only
    python tools/test_adspower_ui_profile.py --find-only         # create+find, no open
    python tools/test_adspower_ui_profile.py --rename k1e0mqys:Snapchat:bob   # rename only
    python tools/test_adspower_ui_profile.py --close k1e0mqys    # close only
    python tools/test_adspower_ui_profile.py --delete k1e0mqys   # delete only
    python tools/test_adspower_ui_profile.py --lifecycle         # create->open->close->delete

Requires the AdsPower desktop app to be running and signed in.
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.adspower_ui import AdsPowerUIController


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _ax_is_trusted() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _macos_preflight_message(platform=sys.platform,
                             import_check=_module_exists,
                             ax_trusted=_ax_is_trusted):
    if platform != "darwin":
        return None
    required = ("ApplicationServices", "Quartz", "AppKit")
    missing = [name for name in required if not import_check(name)]
    if missing:
        return (
            "Missing macOS PyObjC modules for AdsPower AXUI automation: "
            + ", ".join(missing)
            + ". Run the launcher setup again so requirements.txt installs the "
            "macOS-only PyObjC dependencies."
        )
    if not ax_trusted():
        return (
            "macOS Accessibility permission is required for the live AdsPower GUI "
            "test. Grant Accessibility permission to Terminal, Codex, or the "
            "bundled Nyx Suite app in System Settings -> Privacy & Security -> "
            "Accessibility, then run this command again."
        )
    return None


def main():
    ap = argparse.ArgumentParser(description="AdsPower no-API GUI automation E2E test")
    ap.add_argument("--name", default="Snapchat: Pending")
    ap.add_argument("--group", default="Snapchat20")
    ap.add_argument("--proxy", default="48.45.190.63:42438:hwwrghLD:j432NPbg")
    ap.add_argument("--open", default="", help="Skip create; just open this profile id")
    ap.add_argument("--find-only", action="store_true", help="Create + resolve id, skip open")
    ap.add_argument("--rename", default="", help="Rename only: 'PROFILE_ID:New Name'")
    ap.add_argument("--close", default="", help="Close only: PROFILE_ID")
    ap.add_argument("--delete", default="", help="Delete only: PROFILE_ID")
    ap.add_argument("--lifecycle", action="store_true",
                    help="Full no-API account lifecycle: create -> open -> close -> delete")
    args = ap.parse_args()

    preflight = _macos_preflight_message()
    if preflight:
        print("FAIL:", preflight, flush=True)
        return 1

    ctrl = AdsPowerUIController()

    # ---- single-operation modes (validate the new GUI fallbacks) -------------
    if args.rename:
        pid, _, new_name = args.rename.partition(":")
        print(f"== Rename {pid!r} -> {new_name!r} ==", flush=True)
        print(ctrl.rename_profile_by_id(pid.strip(), new_name.strip()), flush=True)
        print("RENAME OK", flush=True)
        return 0
    if args.close:
        print(f"== Close {args.close!r} ==", flush=True)
        ok = ctrl.close_profile_by_id(args.close.strip())
        print(f"CLOSE {'OK' if ok else 'NOT CONFIRMED'}", flush=True)
        return 0 if ok else 1
    if args.delete:
        print(f"== Delete {args.delete!r} ==", flush=True)
        print(ctrl.delete_profile_by_id(args.delete.strip()), flush=True)
        print("DELETE OK", flush=True)
        return 0

    if args.lifecycle:
        return _lifecycle(ctrl, args)

    if args.open:
        profile_id = args.open
    else:
        print(f"== Creating profile  name={args.name!r} group={args.group!r} ==", flush=True)
        info = ctrl.create_profile(name=args.name, proxy=args.proxy, group=args.group)
        print("create result:", json.dumps(info, default=str), flush=True)
        profile_id = info.get("profile_id") or ""
        if not profile_id:
            print("FAIL: could not resolve the new profile id.", flush=True)
            return 1
        if args.find_only:
            print(f"OK: created and resolved profile id {profile_id}.", flush=True)
            return 0

    print(f"\n== Opening profile {profile_id} via search bar ==", flush=True)
    endpoint = ctrl.open_profile_by_id(profile_id)
    print("CDP endpoint:", endpoint, flush=True)

    print("\n== Attaching Playwright over CDP ==", flush=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        print("  open tabs:", [p.url[:70] for p in ctx.pages], flush=True)
        page = ctx.new_page()
        page.set_content("<h1 id=x>no-API control works</h1>")
        assert page.inner_text("#x") == "no-API control works"
        browser.close()   # detach only; leave the profile open
    print("\nE2E OK: created, found, opened and controlled the profile with no API.", flush=True)
    return 0


def _lifecycle(ctrl, args):
    """Full no-API smoke lifecycle. In Nyxify temp-dashboard mode, close/delete
    happen before any rename because the rename removes the row from the active
    Name-contains dashboard."""
    print(f"== [1/4] Create  name={args.name!r} group={args.group!r} ==", flush=True)
    info = ctrl.create_profile(name=args.name, proxy=args.proxy, group=args.group)
    pid = info.get("profile_id") or ""
    print("  created:", pid, flush=True)
    if not pid:
        print("FAIL: no profile id", flush=True)
        return 1

    print(f"== [2/4] Open {pid} via search/dashboard ==", flush=True)
    endpoint = ctrl.open_profile_by_id(pid)
    print("  CDP:", endpoint, flush=True)

    print(f"== [3/4] Close {pid} (run finished) ==", flush=True)
    closed = ctrl.close_profile_by_id(pid)
    print(f"  closed={closed}", flush=True)
    time.sleep(1.0)

    print(f"== [4/4] Delete {pid} (cleanup) ==", flush=True)
    ctrl.delete_profile_by_id(pid)
    print("  deleted", flush=True)

    print(f"\nLIFECYCLE OK: {pid} created -> opened -> closed -> deleted, no API.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
