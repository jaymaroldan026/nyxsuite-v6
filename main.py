import asyncio
import os
import socket
import traceback
from collections import deque

from core.adspower import (
    AdsPowerManager,
    AdsPowerPermissionError,
    AdsPowerProfileNotOpenError,
    AdsPowerUnreachableError,
    _is_permission_error,
)
from core.bitmoji.proxy_failure import detect_proxy_failure_signal
from core.logger import logger
from core import runner_flags
from core.nyx_runtime_config import load_nyx_config
from core.process_utils import LOGS_DIR
from core.queue_store import get_queue_store
from core.task_runner import process_queued_task
from dotenv import load_dotenv

load_dotenv()


POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
DEFAULT_MIN_PENDING_TO_RUN = int(os.getenv("MIN_PENDING_TO_RUN", "10"))
DEFAULT_MAX_PARALLEL_PROFILES = int(os.getenv("MAX_PARALLEL_PROFILES", "10"))
PAUSE_FILE = os.getenv("PAUSE_FILE", str(LOGS_DIR / "bot.paused"))
RUN_REMAINING_FILE = os.getenv("RUN_REMAINING_FILE", str(LOGS_DIR / "run_remaining.flag"))
RUNNER_LOCK_HOST = os.getenv("NYX_RUNNER_LOCK_HOST", "127.0.0.1")
RUNNER_LOCK_PORT = int(os.getenv("NYX_RUNNER_LOCK_PORT", "8864"))


# Single-instance lock shared with the Nyxify runner and the bridge supervisor.
from core.runner_lock import RunnerLock as _RunnerLock


# Tracks the last AdsPower health code we logged so the preflight gate logs the
# block (and the recovery) exactly once per state change, not every poll.
_adspower_health_state = {"code": None}


def adspower_preflight_gate(adspower):
    """Auto-connect probe: confirm AdsPower's Local API is up (keyless /status)
    before draining. Returns True when reachable — no API key needed for
    localhost — and False only when AdsPower is unreachable or the API is
    genuinely permission-denied, in which case tasks stay PENDING and a banner is
    shown. Re-reads saved settings first so any override takes effect without a
    restart, and auto-resumes the moment AdsPower comes back."""
    try:
        adspower.reload_credentials()
    except Exception:
        pass

    result = adspower.preflight_check()
    if result.get("ok"):
        if _adspower_health_state["code"] is not None:
            logger.info("Connected to AdsPower again — resuming the queue.")
            _adspower_health_state["code"] = None
        runner_flags.nyx_clear_health()
        return True

    code = str(result.get("code") or "adspower_error")
    message = str(result.get("message") or "AdsPower is not accepting API calls.")
    runner_flags.nyx_set_health({"code": code, "message": message})
    if _adspower_health_state["code"] != code:
        logger.error(
            f"Waiting for AdsPower ({code}). Tasks stay PENDING — will auto-resume. {message}"
        )
        _adspower_health_state["code"] = code
    return False


def classify_task_failure(error_msg):
    normalized = str(error_msg or "").strip().lower()

    # AdsPower environment/config errors come first — they are NOT per-profile
    # failures and must never be lumped into generic "error".
    if _is_permission_error(normalized) or "9110" in normalized:
        return "adspower_permission"

    if "local api is unreachable" in normalized:
        return "adspower_unreachable"

    if "profile does not exist" in normalized:
        return "profile_missing"

    if detect_proxy_failure_signal(text=error_msg, error=error_msg):
        return "proxy_error"

    bitmoji_failure_tokens = [
        "bitmoji",
        "editor failed to load",
        "page did not become interactive after load",
        "timeout after login redirect",
        "submit_save_confirmation",
        "open_save_confirmation",
        "save confirmation",
    ]
    if any(token in normalized for token in bitmoji_failure_tokens):
        return "bitmoji_failed"

    return "error"

async def process_task(task, store, adspower):
    try:
        await process_queued_task(task, store, adspower, logger)
    except AdsPowerProfileNotOpenError as e:
        # No-API CDP fallback: the Local API is permission-gated but the server
        # is fine — this profile just isn't open in the AdsPower app. Hold ONLY
        # this row PENDING (open it in AdsPower to proceed); do NOT set the global
        # health flag, so other already-open profiles keep running. Re-probed and
        # auto-resumed every cycle, so no "Rerun Failed" is needed.
        profile_id = task["profile_id"]
        task_id = task["id"]
        run_token = task.get("run_token")
        logger.info(
            f"Profile {profile_id} is not open in AdsPower (no-API CDP mode); leaving PENDING: {e}"
        )
        store.update_status(task_id, "PENDING", "waiting_for_profile_open", error=str(e), run_token=run_token)
    except (AdsPowerPermissionError, AdsPowerUnreachableError) as e:
        # AdsPower environment/config problem (no Local API permission, or the
        # app is unreachable). This is NOT a per-profile failure: never mark the
        # row FAILED. Revert it to PENDING and raise the health flag so the main
        # loop's gate pauses draining until AdsPower is healthy again — the user
        # never has to "Rerun Failed" for a config issue.
        profile_id = task["profile_id"]
        task_id = task["id"]
        run_token = task.get("run_token")
        code = "adspower_permission" if isinstance(e, AdsPowerPermissionError) else "adspower_unreachable"
        runner_flags.nyx_set_health({"code": code, "message": str(e)})
        logger.error(f"AdsPower environment error while processing {profile_id}; leaving PENDING: {e}")
        store.update_status(task_id, "PENDING", "blocked_adspower", error=str(e), run_token=run_token)
    except Exception as e:
        profile_id = task["profile_id"]
        task_id = task["id"]
        run_token = task.get("run_token")
        error_msg = str(e)
        logger.error(f"Task failed for {profile_id}: {error_msg}")
        traceback.print_exc()
        updated = store.update_status(
            task_id,
            "FAILED",
            classify_task_failure(error_msg),
            error_msg,
            run_token=run_token,
        )
        if updated is False:
            logger.info(f"Ignored stale exception result for profile {profile_id}")


async def main():

    logger.info("====================================")
    logger.info(" NYX BOT STARTED ")
    logger.info("====================================")

    runner_lock = _RunnerLock(RUNNER_LOCK_HOST, RUNNER_LOCK_PORT)
    if not runner_lock.acquire():
        logger.warning(
            f"Another Nyx runner already holds the lock on {RUNNER_LOCK_HOST}:{RUNNER_LOCK_PORT}. "
            "Exiting this duplicate process."
        )
        return

    try:
        store = get_queue_store()
        adspower = AdsPowerManager()

        # Global Ctrl+F8 pauses/resumes THIS (Nyx) runner, with a tone. The
        # Bitmoji flow polls the pause flag mid-run, so it pauses the current
        # account too — not just the next one. (core/hotkeys.py)
        try:
            from core.hotkeys import start_pause_hotkey
            start_pause_hotkey("nyx")
        except Exception as exc:
            logger.warning(f"Nyx pause hotkey unavailable: {exc}")

        while True:
            try:
                if os.path.exists(PAUSE_FILE):
                    logger.info(f"Bot is paused. Checking again in {POLL_INTERVAL_SECONDS}s.")
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                runtime_config = load_nyx_config()
                min_pending_to_run = int(runtime_config.get("pending_threshold", DEFAULT_MIN_PENDING_TO_RUN) or DEFAULT_MIN_PENDING_TO_RUN)
                concurrency_limit = int(runtime_config.get("max_parallel_profiles", DEFAULT_MAX_PARALLEL_PROFILES) or DEFAULT_MAX_PARALLEL_PROFILES)

                tasks = store.get_pending_tasks()
                run_remaining_requested = os.path.exists(RUN_REMAINING_FILE)

                if not tasks:
                    if run_remaining_requested:
                        try:
                            os.remove(RUN_REMAINING_FILE)
                        except Exception:
                            pass
                    logger.info(f"No PENDING tasks found. Checking again in {POLL_INTERVAL_SECONDS}s.")
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Preflight: never drain the queue while AdsPower rejects API
                # calls (no Local API permission) or is unreachable. Keep tasks
                # PENDING, surface a health banner, and re-probe next cycle —
                # auto-resuming once the user fixes it. Done on a thread so the
                # blocking HTTP probe doesn't stall the event loop.
                if not await asyncio.to_thread(adspower_preflight_gate, adspower):
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                if len(tasks) < min_pending_to_run and not run_remaining_requested:
                    logger.info(
                        f"Waiting for at least {min_pending_to_run} pending tasks before running. "
                        f"Current pending: {len(tasks)}."
                    )
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Flush mode is sticky: once a flush was requested, the entire
                # batch must drain regardless of the live pending threshold.
                # Removing the flag here (before the inner loop) caused the
                # threshold guard below to fire on the next iteration and
                # short-circuit the run, which is why Flush did nothing.
                flush_mode = bool(run_remaining_requested)
                if flush_mode:
                    if len(tasks) < min_pending_to_run:
                        logger.info(
                            f"Manual flush requested. Starting the remaining {len(tasks)} task(s) "
                            "below the normal threshold."
                        )
                    else:
                        logger.info("Manual flush requested.")
                    try:
                        os.remove(RUN_REMAINING_FILE)
                    except Exception:
                        pass

                logger.info(f"{len(tasks)} pending tasks found")
                logger.info(f"Running max {concurrency_limit} profiles in parallel")

                pending_queue = deque(tasks)
                active_tasks = set()

                while pending_queue or active_tasks:
                    runtime_config = load_nyx_config()
                    min_pending_to_run = int(
                        runtime_config.get("pending_threshold", DEFAULT_MIN_PENDING_TO_RUN)
                        or DEFAULT_MIN_PENDING_TO_RUN
                    )
                    concurrency_limit = int(
                        runtime_config.get("max_parallel_profiles", DEFAULT_MAX_PARALLEL_PROFILES)
                        or DEFAULT_MAX_PARALLEL_PROFILES
                    )
                    # If a fresh flush was requested mid-batch, latch back into
                    # flush mode and clear the flag so the threshold guard
                    # cannot stall the new request.
                    if not flush_mode and os.path.exists(RUN_REMAINING_FILE):
                        flush_mode = True
                        try:
                            os.remove(RUN_REMAINING_FILE)
                        except Exception:
                            pass

                    if pending_queue and not flush_mode and len(pending_queue) < min_pending_to_run:
                        if active_tasks:
                            done, active_tasks = await asyncio.wait(
                                active_tasks,
                                return_when=asyncio.FIRST_COMPLETED
                            )

                            for finished_task in done:
                                try:
                                    await finished_task
                                except Exception as task_error:
                                    logger.error(f"Worker task failed unexpectedly: {task_error}")
                            continue

                        logger.info(
                            f"Pending queue fell below the live threshold ({len(pending_queue)}/{min_pending_to_run}). "
                            "Holding the remaining rows until more are added or Flush is used."
                        )
                        break

                    # If AdsPower went unhealthy mid-batch (a worker just hit a
                    # permission/unreachable error and raised the health flag),
                    # stop launching new profiles. The queue is preserved as
                    # PENDING; let active workers finish, then the outer loop's
                    # preflight gate re-probes and resumes once AdsPower recovers.
                    if runner_flags.nyx_get_health():
                        if not active_tasks:
                            break
                    else:
                        while pending_queue and len(active_tasks) < concurrency_limit:
                            task = pending_queue.popleft()
                            active_tasks.add(asyncio.create_task(process_task(task, store, adspower)))

                    if not active_tasks:
                        break

                    done, active_tasks = await asyncio.wait(
                        active_tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for finished_task in done:
                        try:
                            await finished_task
                        except Exception as task_error:
                            logger.error(f"Worker task failed unexpectedly: {task_error}")

                if pending_queue:
                    logger.info(f"Held {len(pending_queue)} queued task(s) for the next scheduling cycle.")
                else:
                    logger.info("All tasks processed.")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

            except Exception as loop_error:
                logger.error(f"Polling loop error: {loop_error}")
                traceback.print_exc()
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.warning("Bot stopped manually.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        runner_lock.release()


if __name__ == "__main__":
    asyncio.run(main())
