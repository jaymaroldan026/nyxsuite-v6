from core.logger import logger
from core.nyxify_task_store import NyxifyTaskStore


READY_LAST_STEPS = {
    "signup_complete",
    "profile_closed",
    "completed",
    "already_has_bitmoji",
}

INCOMPLETE_LAST_STEPS = {
    "",
    "claimed",
    "checking_proxy",
    "creating_adspower_profile",
    "opening_profile",
    "extensions_disabled",
    "signup_handoff",
    "signup_opened",
    "running_signup",
    "fetching_email",
    "fetching_replacement_email",
    "filling_email_verification",
    "awaiting_email_verification",
    "fetching_otp",
    "awaiting_otp",
    "signup_form_submitted",
}


def _normalize(value):
    return str(value or "").strip()


def get_nyxify_profile_guard(profile_id, store=None, strict=False):
    """Decide whether Nyx (Bitmoji) may run on an AdsPower profile.

    Thin wrapper around :func:`_evaluate_guard` that logs every *locked*
    decision (and the reason) so it's clear in the logs why Nyx is holding a
    profile — the previous silent behaviour made the guard look like it "wasn't
    working" when it was in fact correctly waiting on Nyxify.
    """
    result = _evaluate_guard(profile_id, store=store, strict=strict)
    if result.get("locked"):
        try:
            logger.info(
                f"Nyxify guard: holding profile {_normalize(profile_id) or '-'} — {result.get('reason')}"
            )
        except Exception:
            pass
    return result


def _evaluate_guard(profile_id, store=None, strict=False):
    normalized_profile_id = _normalize(profile_id)
    if not normalized_profile_id:
        return {
            "ready": True,
            "locked": False,
            "reason": "No AdsPower profile id provided.",
            "task": None,
        }

    nyxify_store = store or NyxifyTaskStore()
    task = nyxify_store.get_task_by_adspower_profile_id(normalized_profile_id)
    if not task:
        # No Nyxify task matches this profile. Failing OPEN here is what let Nyx
        # run too early during busy batches (an id that hadn't synced yet, or a
        # format/case mismatch). Only fail open when it's actually safe:
        #   * strict mode -> always hold an unknown profile, OR
        #   * Nyxify currently has signups in flight -> hold (likely a race),
        #   * otherwise (standalone Nyx / Nyxify idle) -> allow.
        if strict:
            return {
                "ready": False,
                "locked": True,
                "reason": "Strict guard on: no Nyxify task owns this profile yet.",
                "task": None,
            }
        try:
            inflight = nyxify_store.has_inflight_signups()
        except Exception:
            inflight = False
        if inflight:
            return {
                "ready": False,
                "locked": True,
                "reason": "Nyxify has signups in progress and no task owns this profile yet (id not synced) — holding.",
                "task": None,
            }
        return {
            "ready": True,
            "locked": False,
            "reason": "No active Nyxify task owns this profile.",
            "task": None,
        }

    status = _normalize(task.get("status")).upper()
    last_step = _normalize(task.get("last_step")).lower()

    if status == "DONE" and last_step in READY_LAST_STEPS:
        return {
            "ready": True,
            "locked": False,
            "reason": f"Nyxify completed this profile at {last_step}.",
            "task": task,
        }

    if status == "DONE" and last_step not in READY_LAST_STEPS:
        return {
            "ready": False,
            "locked": True,
            "reason": f"Nyxify row is DONE but not signup-complete yet ({last_step or 'unknown step'}).",
            "task": task,
        }

    if status in {"PENDING", "RUNNING"} or last_step in INCOMPLETE_LAST_STEPS:
        return {
            "ready": False,
            "locked": True,
            "reason": f"Nyxify is still creating this account ({status or 'UNKNOWN'} / {last_step or 'unknown step'}).",
            "task": task,
        }

    if status == "FAILED":
        return {
            "ready": False,
            "locked": True,
            "reason": f"Nyxify failed this account ({last_step or 'unknown step'}).",
            "task": task,
        }

    return {
        "ready": False,
        "locked": True,
        "reason": f"Nyxify has not marked this profile ready ({status or 'UNKNOWN'} / {last_step or 'unknown step'}).",
        "task": task,
    }
