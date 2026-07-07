import asyncio
import os
import uuid

from core.bitmoji_creator import BitmojiCreator
from core.adspower import AdsPowerManager
from core.nyxify_runtime_config import load_nyxify_config
from core.nyxify_task_store import NyxifyTaskStore


# How many profile *starts* (GUI open + Playwright attach) may overlap, and how
# far apart to space them. With the no-API GUI path a whole batch now opens in one
# toolbar click, so opens no longer need to be spread out to avoid GUI races —
# letting them overlap is what lets the AdsPower bulk search/open serve all
# ``max_parallel`` at once instead of one-by-one. The start concurrency therefore
# defaults to ``max_parallel_profiles`` (so 5 parallel -> 5 reach the bulk search
# together); a small stagger only de-thunders the CDP pre-check. Both stay
# env-overridable for tuning.
_ENV_START_CONCURRENCY = os.getenv("PROFILE_START_CONCURRENCY")
PROFILE_START_STAGGER_SECONDS = max(0.0, float(os.getenv("PROFILE_START_STAGGER_SECONDS", "0.15")))
_TERMINAL_CLOSE_RESULTS = {"already_has_bitmoji", "banned_snap", "proxy_error"}
# Results that must never be auto-retried at the profile level: a real account
# state (banned), a dead proxy, the browser being closed out from under us, or a
# success where Bitmoji already exists. Everything else (a generic step failure —
# e.g. a category/trait panel that didn't render in time) is transient and
# succeeds on a fresh re-run, which is exactly the manual "reset failed → rerun"
# workaround, so we do it automatically.
_TERMINAL_RUN_RESULTS = {"already_has_bitmoji", "banned_snap", "proxy_error", "manual_terminate"}
# Extra whole-profile attempts after the first for a generic Bitmoji failure.
NYX_BITMOJI_PROFILE_RETRIES = max(0, int(os.getenv("NYX_BITMOJI_PROFILE_RETRIES", "2")))
NYX_BITMOJI_RETRY_BACKOFF_SECONDS = max(0.0, float(os.getenv("NYX_BITMOJI_RETRY_BACKOFF_SECONDS", "2.0")))
# Bind these to the *running* loop, not the import-time loop. On Python 3.9 a
# module-level asyncio primitive binds to the loop present at import, which is a
# different loop than the one asyncio.run(main()) creates -> "got Future attached
# to a different loop" and every concurrent task but one fails. Build lazily and
# rebuild if the running loop (or the desired size) changes.
_profile_start_semaphore: "asyncio.Semaphore | None" = None
_profile_start_stagger_lock: "asyncio.Lock | None" = None
_profile_start_loop = None
_profile_start_size = None


def _profile_start_concurrency():
    """Desired overlap for profile starts: one-by-one unless explicitly tuned."""
    if _ENV_START_CONCURRENCY:
        try:
            return max(1, int(_ENV_START_CONCURRENCY))
        except ValueError:
            pass
    return 1


def _profile_start_guards():
    global _profile_start_semaphore, _profile_start_stagger_lock, _profile_start_loop
    global _profile_start_size
    loop = asyncio.get_running_loop()
    desired = _profile_start_concurrency()
    if _profile_start_loop is not loop or _profile_start_size != desired:
        _profile_start_semaphore = asyncio.Semaphore(desired)
        _profile_start_stagger_lock = asyncio.Lock()
        _profile_start_loop = loop
        _profile_start_size = desired
    return _profile_start_semaphore, _profile_start_stagger_lock


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _should_close_profile_after_bitmoji(success: bool, last_result: str) -> bool:
    """Close only after Bitmoji is done or the result is a known terminal state.

    Unexpected selector/time-out failures are left open by default so the user can
    inspect the browser and retry without the GUI automation closing it first.
    Set NYX_CLOSE_PROFILE_ON_FAILURE=1 to restore the old always-close behavior.
    """
    if success:
        return True
    if str(last_result or "").strip() in _TERMINAL_CLOSE_RESULTS:
        return True
    return _env_bool("NYX_CLOSE_PROFILE_ON_FAILURE", False)


DEFAULT_SNAPCHAT_PASSWORD = "ABC123wgmi*"
NYXIFY_READY_FOR_NYX_STEPS = {"signup_complete", "profile_closed", "queued_for_nyx"}
# Post-signup steps that can only be reached AFTER the Snapchat account really
# exists (welcome page confirmed the final username). A FAILED row on one of
# these means only the AdsPower bookkeeping (rename/close/handoff) hiccuped —
# the Bitmoji run must still proceed instead of holding forever.
NYXIFY_POST_SIGNUP_FAILURE_STEPS = {
    "profile_rename_failed",
    "nyx_handoff_failed",
    "profile_close_failed",
}
# Transient bookkeeping steps a DONE row passes through while Nyxify is still
# closing/renaming the profile. Nyx holds during these so its GUI open and CDP
# attach never race Nyxify's close/rename clicks on the same row.
NYXIFY_BOOKKEEPING_STEPS = {
    "closing_profile",
    "renaming_profile_for_nyx",
    "queueing_nyx",
}
# Safety valves so a crashed/wedged Nyxify can never park Nyx rows forever:
# a DONE row stuck on a bookkeeping step goes stale after this long...
NYXIFY_BOOKKEEPING_STALE_SECONDS = float(
    os.getenv("NYXIFY_BOOKKEEPING_STALE_SECONDS", "600"))
# ...and an unmatched Nyx row is only held for the id-sync window this long
# (measured from the Nyx row's created_at, which holds never rewrite).
NYXIFY_PROFILE_SYNC_HOLD_MAX_SECONDS = float(
    os.getenv("NYXIFY_PROFILE_SYNC_HOLD_MAX_SECONDS", "900"))


def _iso_age_seconds(value):
    """Seconds since an ISO-8601 UTC timestamp; None when unparseable."""
    from datetime import datetime, timezone

    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except Exception:
        return None


def _get_nyxify_hold_reason(profile_id, nyx_task=None):
    """Return a hold step while Nyxify still owns this profile, or a
    ``fail:<reason>`` marker when the profile's signup terminally failed.

    Nyxify is allowed to create/login the Snapchat account first — Nyx must
    never interrupt an in-flight signup or Nyxify's close/rename bookkeeping on
    the same profile. But every hold here is bounded: once the account really
    exists (or Nyxify demonstrably moved on) the Bitmoji run proceeds, so a
    profile can never sit at "waiting for Nyxify" forever.
    """
    normalized_profile_id = str(profile_id or "").strip()
    if not normalized_profile_id:
        return ""

    try:
        nyxify_store = NyxifyTaskStore()
        nyxify_task = nyxify_store.get_task_by_adspower_profile_id(normalized_profile_id)
        if nyxify_task:
            status = str(nyxify_task.get("status") or "").strip().upper()
            last_step = str(nyxify_task.get("last_step") or "").strip()

            if status == "DONE":
                if last_step in NYXIFY_BOOKKEEPING_STEPS:
                    # Signup succeeded; close/rename still in flight. Hold —
                    # unless the row went stale (Nyxify crashed mid-bookkeeping),
                    # in which case the account is real and Nyx may proceed.
                    age = _iso_age_seconds(nyxify_task.get("updated_at"))
                    if age is not None and age < NYXIFY_BOOKKEEPING_STALE_SECONDS:
                        return "waiting_for_nyxify_success"
                # Any other DONE step means the signup completed and Nyxify is
                # finished with the profile (ready steps, or an unknown step
                # from a newer/older Nyxify) — proceed.
                return ""

            if status == "FAILED":
                if last_step in NYXIFY_POST_SIGNUP_FAILURE_STEPS:
                    # The Snapchat account exists; only AdsPower bookkeeping
                    # failed. Continue with the Bitmoji run.
                    return ""
                # The signup itself failed — there is no account to put a
                # Bitmoji on. Fail the Nyx row (visibly, rerunnable) instead of
                # re-holding it every poll forever.
                return "fail:nyxify_signup_failed"

            # PENDING / RUNNING: account creation is (or may soon be) in
            # progress — never interrupt it.
            return "waiting_for_nyxify_success"

        try:
            continuous_mode = bool(load_nyxify_config().get("continuous_mode_enabled", False))
        except Exception:
            continuous_mode = False
        if continuous_mode and nyxify_store.has_running_signups():
            # No Nyxify row matches this profile. Only an actively RUNNING
            # signup can have created a profile whose id hasn't synced yet, and
            # that window is short — so bound the hold by the Nyx row's age
            # instead of holding every unmatched profile for as long as Nyxify
            # has any work queued (which starved old profiles indefinitely).
            # An unreadable age counts as old: progress beats an unbounded hold.
            age = _iso_age_seconds((nyx_task or {}).get("created_at"))
            if age is not None and age < NYXIFY_PROFILE_SYNC_HOLD_MAX_SECONDS:
                return "waiting_for_nyxify_profile_sync"
    except Exception:
        return ""

    return ""


def resolve_snapchat_credentials(profile_id, logger):
    """Resolve the auto sign-in credentials for a profile whose Snapchat
    session dropped (login page instead of the OAuth consent).

    The Nyxify row for this AdsPower profile is the authoritative source: its
    ``username`` is the real account name confirmed on the welcome page, and
    its ``password`` is the SnapBoard row's Password column — the password the
    account was actually signed up with. Env/default passwords are only
    fallbacks for rows SnapBoard left blank (signup used the default too), and
    a missing username falls back to the browser-context extraction inside
    ``try_auto_snapchat_login``."""
    username = ""
    snapboard_password = ""
    try:
        nyxify_task = NyxifyTaskStore().get_task_by_adspower_profile_id(profile_id)
        if nyxify_task:
            username = str(nyxify_task.get("username") or "").strip()
            snapboard_password = str(nyxify_task.get("password") or "").strip()
    except Exception as exc:
        logger.warning(f"Could not read Nyxify credentials for {profile_id}: {exc}")

    env_password = (
        str(os.getenv("SNAPCHAT_LOGIN_PASSWORD", "") or "").strip()
        or str(os.getenv("SNAPCHAT_DEFAULT_PASSWORD", "") or "").strip()
    )
    if snapboard_password:
        password, source = snapboard_password, "snapboard.password"
    elif env_password:
        password, source = env_password, "env.password"
    else:
        password, source = DEFAULT_SNAPCHAT_PASSWORD, "default.password"

    logger.info(
        f"Prepared Snapchat auto-login credentials for {profile_id} via {source}"
        f"{' with Nyxify username' if username else ''}"
    )
    return {
        "username": username,
        "password": password,
        "source": source,
    }


async def run_profile_task(
    profile_id,
    model,
    logger,
    adspower=None,
    outfit_seed="",
    progress_callback=None,
    manual_queue_mode=False,
    owns_run=None,
):

    manager = adspower or AdsPowerManager()
    snapchat_credentials = resolve_snapchat_credentials(profile_id, logger)
    creator = None
    profile_opened = False
    should_close_profile = False
    last_result = "normal"
    try:
        _semaphore, _stagger_lock = _profile_start_guards()
        async with _semaphore:
            async with _stagger_lock:
                if PROFILE_START_STAGGER_SECONDS > 0:
                    await asyncio.sleep(PROFILE_START_STAGGER_SECONDS)

            ws_endpoint = await asyncio.to_thread(manager.open_profile, profile_id)
            profile_opened = True
            creator = BitmojiCreator(ws_endpoint, logger)
            await creator.start()

        success = await creator.run(
            profile_id,
            model,
            outfit_seed=outfit_seed,
            snapchat_credentials=snapchat_credentials,
            browser_ready=True,
            # Always report progress (not just in manual-queue mode) so the task
            # store's last_step tracks the live step and a FAILED row keeps the
            # exact step it died on (e.g. "face_hair_style").
            progress_callback=progress_callback,
            manual_queue_mode=manual_queue_mode,
        )
        last_result = getattr(creator, "last_result", "normal")
        should_close_profile = _should_close_profile_after_bitmoji(success, last_result)
        return success, last_result
    except Exception:
        if creator is not None:
            last_result = getattr(creator, "last_result", last_result)
        should_close_profile = _should_close_profile_after_bitmoji(False, last_result)
        raise
    finally:
        if profile_opened:
            try:
                if not should_close_profile:
                    logger.info(
                        f"Left AdsPower profile {profile_id} open because Bitmoji "
                        f"did not finish cleanly (last_result={last_result})."
                    )
                elif owns_run is None or owns_run():
                    await asyncio.to_thread(manager.close_profile, profile_id)
                    logger.info(f"Closed AdsPower profile {profile_id}")
                else:
                    logger.info(f"Skipped closing AdsPower profile {profile_id} because a newer run owns it")
            except Exception as close_error:
                logger.warning(f"Could not close profile {profile_id}: {close_error}")


async def process_queued_task(task, store, adspower, logger):

    task_id = task["id"]
    profile_id = task["profile_id"]
    model = task["model"]
    outfit_seed = task.get("outfit_seed", "")
    source = str(task.get("source", "") or "").strip().lower()
    manual_queue_mode = source == "manual_queue"

    hold_reason = _get_nyxify_hold_reason(profile_id, task)
    if hold_reason.startswith("fail:"):
        failed_step = hold_reason.split(":", 1)[1] or "nyxify_signup_failed"
        logger.error(
            f"Nyx profile {profile_id} cannot run: the Nyxify signup for it failed "
            f"before an account existed. Marking FAILED ({failed_step})."
        )
        store.update_status(
            task_id, "FAILED", failed_step,
            error="Nyxify signup failed for this profile before the Snapchat account was created.",
        )
        return
    if hold_reason:
        logger.info(f"Holding Nyx profile {profile_id}: {hold_reason}")
        store.update_status(task_id, "PENDING", hold_reason, error="")
        # A hold consumes this batch's flush latch; re-arm it so the row is
        # retried on the next poll even when the queue sits below the start
        # threshold (otherwise the last continuous-mode handoff of a batch
        # could park below the threshold forever after its one hold).
        try:
            from core import runner_flags

            runner_flags.nyx_request_flush()
        except Exception:
            pass
        return

    logger.info(f"Starting task for profile {profile_id}")
    run_token = uuid.uuid4().hex
    task["run_token"] = run_token

    if not store.begin_run(task_id, run_token, step="opening_profile"):
        logger.info(f"Skipped stale or already-claimed task for profile {profile_id}")
        return

    store.update_last_step(task_id, "connecting_playwright", run_token=run_token)
    store.update_last_step(task_id, "running_bitmoji_flow", run_token=run_token)

    # Remember the most recent step so a FAILED row reports exactly where it
    # stopped (e.g. "face_hair_style", "saving_bitmoji") instead of a generic
    # "bitmoji_failed".
    last_step_seen = {"value": "running_bitmoji_flow"}

    def progress_callback(step):
        try:
            normalized = str(step or "").strip()
            if normalized:
                last_step_seen["value"] = normalized
            store.update_last_step(task_id, step, run_token=run_token)
        except Exception as callback_error:
            logger.warning(f"Could not update task step for {profile_id}: {callback_error}")

    # Whole-profile auto-retry: a generic Bitmoji step failure (a category or
    # trait panel that didn't render in time) almost always succeeds on a fresh
    # re-run — the same thing a user does by hand with "reset failed → rerun".
    # Do it automatically before marking the row FAILED. Terminal results
    # (banned / dead proxy / browser closed / already-has-bitmoji) break out
    # immediately and are never retried.
    max_attempts = 1 + NYX_BITMOJI_PROFILE_RETRIES
    success, last_result = False, "normal"
    for attempt in range(1, max_attempts + 1):
        # Bail if the row was re-claimed by a newer run while we were working.
        if not store.is_current_run(task_id, run_token):
            logger.info(f"Skipped stale/again-claimed task for profile {profile_id} before attempt {attempt}")
            return

        success, last_result = await run_profile_task(
            profile_id,
            model,
            logger,
            adspower=adspower,
            outfit_seed=outfit_seed,
            progress_callback=progress_callback,
            manual_queue_mode=manual_queue_mode,
            owns_run=lambda: store.is_current_run(task_id, run_token),
        )

        if success or last_result in _TERMINAL_RUN_RESULTS:
            break

        if attempt < max_attempts:
            logger.warning(
                f"Bitmoji attempt {attempt}/{max_attempts} failed for profile {profile_id} "
                f"at step '{last_step_seen['value']}' (last_result={last_result}); "
                "retrying the whole profile automatically."
            )
            store.update_last_step(task_id, "retrying_bitmoji_flow", run_token=run_token)
            if NYX_BITMOJI_RETRY_BACKOFF_SECONDS > 0:
                await asyncio.sleep(NYX_BITMOJI_RETRY_BACKOFF_SECONDS)

    if success or last_result == "already_has_bitmoji":
        completed_step = "already_has_bitmoji" if last_result == "already_has_bitmoji" else "completed"
        if store.update_status(task_id, "DONE", completed_step, run_token=run_token):
            logger.info(f"Task completed for profile {profile_id}")
        else:
            logger.info(f"Ignored stale completion for profile {profile_id}")
        return

    if last_result == "banned_snap":
        banned_error = "Snapchat account banned (authorization error during Bitmoji creation)."
        if store.update_status(task_id, "FAILED", "banned_snap", error=banned_error, run_token=run_token):
            logger.error(f"Profile {profile_id} marked BANNED (Snapchat authorization error)")
            # Reflect the ban on SnapBoard (and the local Nyxify row) so the
            # account is flagged and never re-signed-up. Best-effort: a missing
            # SnapBoard tab or row must never break the run.
            try:
                from core.snapboard_status import mark_account_banned

                mark_account_banned(profile_id, logger=logger)
            except Exception as banned_error_exc:
                logger.warning(
                    f"Could not update SnapBoard banned status for {profile_id}: {banned_error_exc}"
                )
        else:
            logger.info(f"Ignored stale banned result for profile {profile_id}")
        return

    if last_result == "proxy_error":
        proxy_error = "Profile proxy failure persisted through the recovery window (no internet / ERR_PROXY_CONNECTION_FAILED)."
        if store.update_status(task_id, "FAILED", "proxy_error", error=proxy_error, run_token=run_token):
            logger.error(f"Profile {profile_id} marked FAILED (proxy_error)")
        else:
            logger.info(f"Ignored stale proxy result for profile {profile_id}")
        return

    if last_result == "manual_terminate":
        manual_error = "AdsPower profile was closed/terminated manually during Bitmoji creation."
        if store.update_status(task_id, "FAILED", "manual_terminate", error=manual_error, run_token=run_token):
            logger.warning(f"Profile {profile_id} marked FAILED (manual_terminate)")
        else:
            logger.info(f"Ignored stale manual-terminate result for profile {profile_id}")
        return

    failed_step = last_step_seen["value"] or "bitmoji_failed"
    if store.update_status(task_id, "FAILED", failed_step, run_token=run_token):
        logger.error(f"Bitmoji failed for profile {profile_id} at step '{failed_step}'")
    else:
        logger.info(f"Ignored stale failure for profile {profile_id}")
