# CDP Attach Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prevent Continuous Mode from parking forever when AdsPower exposes a live CDP endpoint but Playwright cannot complete `connect_over_cdp`.

**Architecture:** Treat Playwright CDP attach timeout as a browser-session recovery problem, not a Bitmoji auth problem. Nyx should surface a clear step, fail fast, recycle the AdsPower profile once, and requeue orphaned `RUNNING` rows after runner restart.

**Tech Stack:** Python async runner, Playwright, SQLite task stores, existing AdsPower GUI/API manager, pytest/unittest.

---

## Evidence From `k1evn703`

- Nyxify task `1550` created Snapchat account `arichloinked`, renamed AdsPower profile `k1evn703` to `Snapchat: arichloinked`, and queued Nyx with `source='nyxify_continuous'`, `priority=100`.
- Nyx task `2428` is `RUNNING`, `last_step='running_bitmoji_flow'`, with no error.
- AdsPower CDP HTTP endpoints for port `58328` respond to `/json/version` and `/json/list`.
- Raw CDP websocket responds to `Browser.getVersion` and `Target.getTargets`.
- Playwright `connect_over_cdp` hangs until its 180 second timeout and repeats four times, so one attempt can consume about 12 minutes before the whole-profile retry starts.
- Continuous Mode waits correctly because it sees an active continuous Nyx handoff, but the UI does not reveal the actual CDP attach retry state.

## Files

- Modify: `core/bitmoji_creator.py`
- Modify: `core/task_runner.py`
- Modify: `core/task_store.py`
- Modify: `main.py`
- Test: `tests/test_bitmoji_cdp_attach_recovery.py`
- Test: `tests/test_nyx_auth_phase_routing.py`
- Test: `tests/test_nyx_run_now_priority.py`

---

### Task 1: Add A Typed CDP Attach Timeout

**Files:**
- Modify: `core/bitmoji_creator.py`
- Test: `tests/test_bitmoji_cdp_attach_recovery.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_bitmoji_cdp_attach_recovery.py` with:

```python
import asyncio
import sys
import types
import unittest
from unittest import mock

if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pw_async = types.ModuleType("playwright.async_api")
    _pw_async.async_playwright = lambda: None
    sys.modules["playwright"] = _pw
    sys.modules["playwright.async_api"] = _pw_async

from core.bitmoji_creator import BitmojiCreator, CdpAttachTimeoutError


class _FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(str(message))


class _HangingChromium:
    async def connect_over_cdp(self, _endpoint):
        await asyncio.sleep(60)


class _FakePlaywright:
    def __init__(self):
        self.chromium = _HangingChromium()
        self.stopped = False

    async def stop(self):
        self.stopped = True


class CdpAttachRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_attach_timeout_raises_typed_error_fast(self):
        playwright = _FakePlaywright()
        logger = _FakeLogger()

        async def fake_start():
            return playwright

        with mock.patch(
            "core.bitmoji_creator.async_playwright",
            return_value=types.SimpleNamespace(start=fake_start),
        ), mock.patch.object(BitmojiCreator, "CDP_ATTACH_TIMEOUT_SECONDS", 0.01), mock.patch.object(
            BitmojiCreator, "CDP_ATTACH_ATTEMPTS", 1
        ):
            creator = BitmojiCreator("ws://127.0.0.1:58328/devtools/browser/test", logger)
            with self.assertRaises(CdpAttachTimeoutError) as raised:
                await creator.start()

        self.assertIn("Timed out connecting to AdsPower CDP", str(raised.exception))
        self.assertTrue(playwright.stopped)
        self.assertTrue(any("CDP connect retry 1/1" in line for line in logger.warnings))
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bitmoji_cdp_attach_recovery.py
```

Expected: import or assertion failure because `CdpAttachTimeoutError`, `CDP_ATTACH_TIMEOUT_SECONDS`, and `CDP_ATTACH_ATTEMPTS` do not exist yet.

- [x] **Step 3: Implement the typed error and bounded attach**

In `core/bitmoji_creator.py`, add near the imports:

```python
class CdpAttachTimeoutError(Exception):
    """Raised when AdsPower CDP is reachable but Playwright cannot attach."""
```

Inside `class BitmojiCreator`, add class attributes:

```python
    CDP_ATTACH_TIMEOUT_SECONDS = float(os.getenv("NYX_CDP_ATTACH_TIMEOUT_SECONDS", "45"))
    CDP_ATTACH_ATTEMPTS = max(1, int(os.getenv("NYX_CDP_ATTACH_ATTEMPTS", "2") or "2"))
```

Replace the fixed `for attempt in range(4):` block in `start()` with:

```python
        for attempt in range(self.CDP_ATTACH_ATTEMPTS):
            try:
                self.browser = await asyncio.wait_for(
                    self.playwright.chromium.connect_over_cdp(self.ws_endpoint),
                    timeout=self.CDP_ATTACH_TIMEOUT_SECONDS,
                )

                for _ in range(20):
                    if self.browser.contexts:
                        self.context = self.browser.contexts[0]
                        await apply_native_color_scheme_to_context(self.context, logger=self.logger)
                        await maximize_browser_window(self.browser, logger=self.logger)
                        return
                    await asyncio.sleep(0.25)

                raise Exception("Connected to browser, but no browser context became ready.")
            except asyncio.TimeoutError as exc:
                last_error = exc
                if self.logger:
                    self.logger.warning(
                        f"CDP connect retry {attempt + 1}/{self.CDP_ATTACH_ATTEMPTS} "
                        f"timed out after {self.CDP_ATTACH_TIMEOUT_SECONDS:.0f}s for websocket {self.ws_endpoint}"
                    )
                await asyncio.sleep(1.0 + (attempt * 0.4))
            except Exception as exc:
                last_error = exc
                if self.logger:
                    self.logger.warning(
                        f"CDP connect retry {attempt + 1}/{self.CDP_ATTACH_ATTEMPTS} "
                        f"failed for websocket {self.ws_endpoint}: {exc}"
                    )
                await asyncio.sleep(1.0 + (attempt * 0.4))

        try:
            await self.stop()
        finally:
            raise CdpAttachTimeoutError(
                f"Timed out connecting to AdsPower CDP after {self.CDP_ATTACH_ATTEMPTS} "
                f"attempt(s): {last_error}"
            )
```

- [x] **Step 4: Run the test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bitmoji_cdp_attach_recovery.py
```

Expected: pass.

---

### Task 2: Recycle AdsPower Profile Before Retrying A CDP Attach Failure

**Files:**
- Modify: `core/task_runner.py`
- Test: `tests/test_nyx_auth_phase_routing.py`

- [x] **Step 1: Write the failing test**

Append to `AuthPhaseRoutingTests` in `tests/test_nyx_auth_phase_routing.py`:

```python
    def test_cdp_attach_timeout_recycles_profile_before_retry(self):
        from core.bitmoji_creator import CdpAttachTimeoutError

        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1abc", "model": "willow"}
        attempts = []
        manager = mock.Mock()

        async def fake_run_profile_task(*args, **kwargs):
            attempts.append(args)
            if len(attempts) == 1:
                raise CdpAttachTimeoutError("Timed out connecting to AdsPower CDP")
            return (True, "normal")

        with mock.patch.object(task_runner, "run_profile_task", fake_run_profile_task), \
             mock.patch.object(task_runner, "_get_nyxify_hold_reason", lambda profile_id, nyx_task=None: ""), \
             mock.patch.object(task_runner, "NYX_BITMOJI_PROFILE_RETRIES", 1), \
             mock.patch.object(task_runner, "NYX_BITMOJI_RETRY_BACKOFF_SECONDS", 0):
            asyncio.run(task_runner.process_queued_task(task, store, adspower=manager, logger=_FakeLogger()))

        self.assertEqual(len(attempts), 2)
        self.assertEqual(manager.close_profile.call_count, 1)
        self.assertIn(
            "recovering_cdp_attach",
            [call["step"] for call in store.last_step_calls],
        )
        self.assertEqual(store.status_calls[-1]["status"], "DONE")
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_nyx_auth_phase_routing.py::AuthPhaseRoutingTests::test_cdp_attach_timeout_recycles_profile_before_retry
```

Expected: failure because `process_queued_task()` does not close/recycle on typed CDP attach timeout.

- [x] **Step 3: Implement recovery in the retry handler**

In `core/task_runner.py`, import the typed error:

```python
from core.bitmoji_creator import BitmojiCreator, CdpAttachTimeoutError
```

Inside `process_queued_task()`, in the `except Exception as attempt_error:` block before the generic retry log, add:

```python
            if isinstance(attempt_error, CdpAttachTimeoutError):
                logger.warning(
                    f"CDP attach timed out for profile {profile_id}; recycling the AdsPower "
                    "browser before retrying the Bitmoji flow."
                )
                store.update_last_step(task_id, "recovering_cdp_attach", run_token=run_token)
                try:
                    await asyncio.to_thread(adspower.close_profile, profile_id)
                except Exception as close_error:
                    logger.warning(f"Could not close profile {profile_id} during CDP recovery: {close_error}")
```

- [x] **Step 4: Run the targeted test**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_nyx_auth_phase_routing.py::AuthPhaseRoutingTests::test_cdp_attach_timeout_recycles_profile_before_retry
```

Expected: pass.

---

### Task 3: Requeue Orphaned Nyx `RUNNING` Rows On Startup

**Files:**
- Modify: `core/task_store.py`
- Modify: `main.py`
- Test: `tests/test_nyx_run_now_priority.py`

- [x] **Step 1: Write the failing test**

Append to `NyxRunNowPriorityTests` in `tests/test_nyx_run_now_priority.py`:

```python
    def test_startup_requeues_orphaned_running_continuous_handoff(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(db_path=str(Path(tmp) / "nyx_tasks.db"))
            task_id, _ = store.upsert_task(
                profile_id="k1continuous",
                model="Chloe",
                source="nyxify_continuous",
                priority=100,
            )
            store.begin_run(task_id, "dead-run", step="running_bitmoji_flow")

            requeued = main._reset_orphaned_running_tasks_on_startup(store)

            row = store.get_task_by_profile_id("k1continuous")
            self.assertEqual(requeued, 1)
            self.assertEqual(row["status"], "PENDING")
            self.assertEqual(row["last_step"], "requeued_after_runner_restart")
            self.assertEqual(row["priority"], 100)
            self.assertEqual(row["source"], "nyxify_continuous")
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_nyx_run_now_priority.py::NyxRunNowPriorityTests::test_startup_requeues_orphaned_running_continuous_handoff
```

Expected: failure because the helper does not exist.

- [x] **Step 3: Add a store helper**

In `core/task_store.py`, add:

```python
    def requeue_running_tasks_after_runner_restart(self):
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING',
                    run_token = '',
                    last_step = 'requeued_after_runner_restart',
                    error = '',
                    completed_at = '',
                    updated_at = ?
                WHERE status = 'RUNNING'
                """,
                (now,),
            )
            return cursor.rowcount
```

- [x] **Step 4: Add and call the startup helper**

In `main.py`, add near the queue helpers:

```python
def _reset_orphaned_running_tasks_on_startup(store):
    try:
        return int(store.requeue_running_tasks_after_runner_restart() or 0)
    except Exception as exc:
        logger.warning(f"Could not requeue orphaned Nyx RUNNING rows on startup: {exc}")
        return 0
```

Call it after `store = get_queue_store()`:

```python
        requeued = _reset_orphaned_running_tasks_on_startup(store)
        if requeued:
            logger.info(f"Requeued {requeued} orphaned Nyx RUNNING task(s) after runner startup.")
```

- [x] **Step 5: Run the targeted test**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_nyx_run_now_priority.py::NyxRunNowPriorityTests::test_startup_requeues_orphaned_running_continuous_handoff
```

Expected: pass.

---

### Task 4: Focused Verification

**Files:**
- No source changes.

- [x] **Step 1: Run focused regression tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_bitmoji_cdp_attach_recovery.py tests/test_nyx_auth_phase_routing.py tests/test_nyx_run_now_priority.py tests/test_adspower_cdp_fallback.py
```

Expected: all pass.

- [x] **Step 2: Compile touched Python files**

Run:

```bash
.venv/bin/python -m py_compile core/bitmoji_creator.py core/task_runner.py core/task_store.py main.py tests/test_bitmoji_cdp_attach_recovery.py
```

Expected: exit code 0.

- [x] **Step 3: Check whitespace**

Run:

```bash
git diff --check -- core/bitmoji_creator.py core/task_runner.py core/task_store.py main.py tests/test_bitmoji_cdp_attach_recovery.py tests/test_nyx_auth_phase_routing.py tests/test_nyx_run_now_priority.py
```

Expected: no output.

---

## Operational Recovery For Current `k1evn703`

Do not mark the Snapchat account failed. It already exists.

Recommended manual recovery:

1. Stop Nyx only.
2. Close AdsPower profile `k1evn703`.
3. Reopen AdsPower profile `k1evn703`.
4. Relaunch or rerun the Nyx row.
5. Confirm the row moves past `running_bitmoji_flow` into `oauth_continue`, `gender_editor_handoff`, or avatar steps.

The code fix above automates this exact recovery when Playwright CDP attach times out.
