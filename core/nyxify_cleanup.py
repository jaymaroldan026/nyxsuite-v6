"""Shared cleanup helpers for Nyxify AdsPower profiles."""

CLEANUP_DELETE_FAILED_STEP = "cleanup_delete_failed"
CLEANUP_DELETED_STEP = "cleanup_deleted"


def _safe_text(value):
    return str(value or "").strip()


def _log(log, level, message):
    if log is None:
        return
    try:
        getattr(log, level)(message)
    except Exception:
        pass


def cleanup_delete_failed_error(profile_id, delete_error, reason=""):
    normalized_profile_id = _safe_text(profile_id)
    normalized_reason = _safe_text(reason)
    normalized_delete_error = _safe_text(delete_error) or "AdsPower did not confirm profile deletion."
    prefix = f"AdsPower cleanup delete failed for profile {normalized_profile_id}"
    if normalized_reason:
        prefix += f" after {normalized_reason}"
    return f"{prefix}. Profile id was kept for manual orphan cleanup. Delete error: {normalized_delete_error}"


def close_and_delete_profile(adspower, profile_id, log=None, task_id=None, row_key="", reason=""):
    normalized_profile_id = _safe_text(profile_id)
    normalized_row_key = _safe_text(row_key)
    normalized_reason = _safe_text(reason) or "cleanup"
    result = {
        "profile_id": normalized_profile_id,
        "row_key": normalized_row_key,
        "task_id": task_id,
        "reason": normalized_reason,
        "closed": False,
        "close_error": "",
        "deleted": False,
        "delete_error": "",
        "delete_result": None,
    }
    context = (
        f"task_id={task_id} row_key={normalized_row_key or '-'} "
        f"profile_id={normalized_profile_id or '-'} reason={normalized_reason}"
    )

    if not normalized_profile_id:
        result["delete_error"] = "AdsPower profile id is required."
        _log(log, "warning", f"Nyxify cleanup skipped because profile id is empty ({context}).")
        return result

    try:
        adspower.close_profile(normalized_profile_id)
        result["closed"] = True
        _log(log, "info", f"Nyxify cleanup closed AdsPower profile ({context}).")
    except Exception as exc:
        result["close_error"] = str(exc) or repr(exc)
        _log(
            log,
            "warning",
            f"Nyxify cleanup could not close AdsPower profile ({context}): {result['close_error']}",
        )

    try:
        data = adspower.delete_profile(normalized_profile_id)
        if not isinstance(data, dict) or data.get("code") != 0:
            raise RuntimeError(f"AdsPower delete did not confirm success: {data}")
        result["deleted"] = True
        result["delete_result"] = data
        _log(log, "info", f"Nyxify cleanup deleted AdsPower profile ({context}).")
    except Exception as exc:
        result["delete_error"] = str(exc) or repr(exc)
        _log(
            log,
            "warning",
            f"Nyxify cleanup could not delete AdsPower profile ({context}): {result['delete_error']}",
        )

    return result


def _task_profile_id(row):
    return _safe_text((row or {}).get("adspower_profile_id")) or _safe_text((row or {}).get("adspower_id"))


def cleanup_orphan_failed_profiles(store, adspower, limit=500, log=None):
    rows = store.get_cleanup_delete_failed_tasks(limit=limit)
    deleted = 0
    failed = 0
    results = []

    for row in rows:
        task_id = row.get("id")
        row_key = _safe_text(row.get("row_key"))
        profile_id = _task_profile_id(row)
        cleanup_result = close_and_delete_profile(
            adspower,
            profile_id,
            log=log,
            task_id=task_id,
            row_key=row_key,
            reason=CLEANUP_DELETE_FAILED_STEP,
        )

        if cleanup_result["deleted"]:
            deleted += 1
            store.update_task_state(
                task_id,
                status="FAILED",
                last_step=CLEANUP_DELETED_STEP,
                error="",
                adspower_id="",
                adspower_profile_id="",
                adspower_name="",
                adspower_group="",
                tags=[],
            )
            final_state = CLEANUP_DELETED_STEP
        else:
            failed += 1
            error_message = cleanup_delete_failed_error(
                profile_id,
                cleanup_result.get("delete_error"),
                CLEANUP_DELETE_FAILED_STEP,
            )
            store.update_task_state(
                task_id,
                status="FAILED",
                last_step=CLEANUP_DELETE_FAILED_STEP,
                error=error_message,
            )
            final_state = CLEANUP_DELETE_FAILED_STEP

        results.append(
            {
                "task_id": task_id,
                "row_key": row_key,
                "profile_id": profile_id,
                "closed": cleanup_result["closed"],
                "deleted": cleanup_result["deleted"],
                "close_error": cleanup_result["close_error"],
                "delete_error": cleanup_result["delete_error"],
                "final_state": final_state,
            }
        )

    return {
        "ok": failed == 0,
        "attempted": len(rows),
        "deleted": deleted,
        "failed": failed,
        "rows": results,
    }
