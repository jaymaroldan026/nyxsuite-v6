import json
import os
import urllib.request
from pathlib import Path

from core import runner_flags
from core.process_utils import APP_DATA_DIR


NYX_LOCAL_API_URL = os.getenv("NYX_LOCAL_API_URL", "http://127.0.0.1:8865").rstrip("/")
NYX_TASK_DB_PATH = Path(os.getenv("NYX_TASK_DB_PATH", str(APP_DATA_DIR / "data" / "nyx_tasks.db")))
_NYX_LOCAL_API_TOKEN = os.getenv("NYX_LOCAL_API_TOKEN") or os.getenv("NYXSUITE_TOKEN") or ""
_LOCAL_API_TOKEN_CACHED = False


def _api_json(path, payload=None, token="", timeout=8):
    url = f"{NYX_LOCAL_API_URL}{path}"
    headers = {"Content-Type": "application/json"}
    method = "GET" if payload is None else "POST"
    data = None
    if token:
        headers["X-Nyx-Token"] = token
    if payload is not None:
        body = dict(payload or {})
        if token:
            body["token"] = token
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _ensure_nyx_local_api_token():
    global _NYX_LOCAL_API_TOKEN, _LOCAL_API_TOKEN_CACHED
    if _LOCAL_API_TOKEN_CACHED:
        return _NYX_LOCAL_API_TOKEN
    if _NYX_LOCAL_API_TOKEN:
        _LOCAL_API_TOKEN_CACHED = True
        return _NYX_LOCAL_API_TOKEN
    try:
        data = _api_json("/token", timeout=3)
        token = str(data.get("token") or "").strip()
        if token:
            _NYX_LOCAL_API_TOKEN = token
            _LOCAL_API_TOKEN_CACHED = True
    except Exception:
        pass
    return _NYX_LOCAL_API_TOKEN


def _queue_direct(profile_id, model):
    from core.task_store import TaskStore

    store = TaskStore(db_path=str(NYX_TASK_DB_PATH))
    _task_id, action = store.upsert_task(
        profile_id=profile_id,
        model=model,
        gender="female",
        status="PENDING",
        source="nyxify_continuous",
    )
    runner_flags.nyx_request_flush()
    return action


def enqueue_profile_for_nyx(profile_id, model, logger=None):
    normalized_profile_id = str(profile_id or "").strip()
    normalized_model = str(model or "").strip()
    if not normalized_profile_id:
        raise ValueError("AdsPower profile id is required for Nyx handoff.")
    if not normalized_model:
        raise ValueError("Model is required for Nyx handoff.")

    api_error = None
    try:
        token = _ensure_nyx_local_api_token()
        queue_result = _api_json(
            "/queue/upsert",
            {"entries": [{"profile_id": normalized_profile_id, "model": normalized_model}]},
            token=token,
        )
        if not queue_result.get("ok"):
            raise RuntimeError(queue_result.get("error") or "Nyx queue upsert failed.")

        start_result = _api_json("/bot/finish_remaining", {}, token=token)
        if not start_result.get("ok"):
            raise RuntimeError(start_result.get("error") or "Nyx start/flush request failed.")

        if logger:
            logger.info(
                f"Queued AdsPower profile {normalized_profile_id} for Nyx Bitmoji creation via local API."
            )
        return {
            "ok": True,
            "method": "api",
            "queue_result": queue_result,
            "start_result": start_result,
        }
    except Exception as exc:
        api_error = exc
        if logger:
            logger.warning(
                f"Nyx local API handoff failed for {normalized_profile_id}; "
                f"falling back to direct queue write: {exc}"
            )

    try:
        action = _queue_direct(normalized_profile_id, normalized_model)
        if logger:
            logger.warning(
                f"Queued AdsPower profile {normalized_profile_id} for Nyx directly "
                "and requested a flush flag. Start Nyx from the dashboard if it is not already running."
            )
        return {
            "ok": True,
            "method": "direct",
            "action": action,
            "api_error": str(api_error or ""),
            "start_requested": False,
        }
    except Exception as direct_exc:
        if logger:
            logger.error(f"Could not hand AdsPower profile {normalized_profile_id} to Nyx: {direct_exc}")
        return {
            "ok": False,
            "method": "failed",
            "api_error": str(api_error or ""),
            "error": str(direct_exc or ""),
        }
