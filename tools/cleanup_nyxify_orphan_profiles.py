import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.adspower import AdsPowerManager
from core.logger import logger
from core.nyxify_cleanup import (
    CLEANUP_DELETED_STEP,
    cleanup_delete_failed_error,
    close_and_delete_profile,
)
from core.nyxify_task_store import NyxifyTaskStore


def _normalize_ids(values):
    profile_ids = []
    seen = set()
    for value in values or []:
        for part in str(value or "").replace(",", " ").split():
            profile_id = part.strip()
            if profile_id and profile_id not in seen:
                seen.add(profile_id)
                profile_ids.append(profile_id)
    return profile_ids


def _update_attached_row(store, profile_id, cleanup_result):
    row = store.get_task_by_adspower_profile_id(profile_id)
    if not row:
        return None

    task_id = row.get("id")
    if cleanup_result.get("deleted"):
        store.update_task_state(
            task_id,
            status=row.get("status") or "FAILED",
            last_step=CLEANUP_DELETED_STEP,
            error="",
            adspower_id="",
            adspower_profile_id="",
            adspower_name="",
            adspower_group="",
            tags=[],
        )
    else:
        store.update_task_state(
            task_id,
            status="FAILED",
            last_step="cleanup_delete_failed",
            error=cleanup_delete_failed_error(
                profile_id,
                cleanup_result.get("delete_error"),
                "manual_orphan_cleanup",
            ),
        )

    return {"task_id": task_id, "row_key": row.get("row_key")}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Safely close and delete explicit Nyxify orphan AdsPower profile IDs."
    )
    parser.add_argument("profile_ids", nargs="+", help="AdsPower profile IDs, separated by spaces or commas.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually close and delete profiles. Without this flag the command is a dry run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    args = parser.parse_args(argv)

    profile_ids = _normalize_ids(args.profile_ids)
    if not profile_ids:
        parser.error("At least one AdsPower profile ID is required.")

    if not args.execute:
        output = {
            "ok": True,
            "dry_run": True,
            "profile_ids": profile_ids,
            "message": "Dry run only. Re-run with --execute to close and delete these profiles.",
        }
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print(output["message"])
            for profile_id in profile_ids:
                print(f"- {profile_id}")
        return 0

    adspower = AdsPowerManager()
    store = NyxifyTaskStore()
    rows = []
    deleted = 0
    failed = 0

    for profile_id in profile_ids:
        cleanup_result = close_and_delete_profile(
            adspower,
            profile_id,
            log=logger,
            reason="manual_orphan_cleanup",
        )
        attached_row = _update_attached_row(store, profile_id, cleanup_result)
        if cleanup_result.get("deleted"):
            deleted += 1
        else:
            failed += 1
        rows.append(
            {
                "profile_id": profile_id,
                "closed": cleanup_result.get("closed"),
                "deleted": cleanup_result.get("deleted"),
                "close_error": cleanup_result.get("close_error"),
                "delete_error": cleanup_result.get("delete_error"),
                "attached_row": attached_row,
            }
        )

    output = {
        "ok": failed == 0,
        "dry_run": False,
        "attempted": len(profile_ids),
        "deleted": deleted,
        "failed": failed,
        "rows": rows,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"Deleted {deleted} of {len(profile_ids)} AdsPower profile(s).")
        for row in rows:
            status = "deleted" if row["deleted"] else f"failed: {row['delete_error']}"
            print(f"- {row['profile_id']}: {status}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
