# Nyxify Parallel Cookie Warmup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Visit Nyxify cookie warmup sites in capped parallel tabs and close all warmup tabs before Snapchat signup opens.

**Architecture:** Keep `nyxify_runner.py` unchanged because it already waits for `warm_ads_profile_cookies(...)` before opening Snapchat. Change `core/adspower_extension_cleanup.py` so `_warm_ads_profile_cookies(...)` schedules per-site workers through a semaphore and performs final page cleanup after all workers finish.

**Tech Stack:** Python async code, Playwright browser contexts, `unittest` with `unittest.mock`.

---

## File Structure

- Modify `core/adspower_extension_cleanup.py`: add the concurrency env setting and capped parallel warmup orchestration.
- Modify `tests/test_nyxify_cookie_warmup.py`: add async unit tests for capped concurrency, cleanup, and worker failure handling.

### Task 1: Add Failing Tests For Capped Parallel Warmup

**Files:**
- Modify: `tests/test_nyxify_cookie_warmup.py`

- [ ] **Step 1: Add async fake page/context helpers and a concurrency test**

```python
class _WarmupPage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


class _WarmupContext:
    def __init__(self, baseline_pages=None):
        self.pages = list(baseline_pages or [])

    async def new_page(self):
        page = _WarmupPage()
        self.pages.append(page)
        return page
```

```python
async def test_cookie_warmup_runs_sites_with_concurrency_cap(self):
    active = 0
    max_active = 0
    started = []

    async def fake_warm_site(_context, url, _duration, _logger, _profile_id):
        nonlocal active, max_active
        started.append(url)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    with mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MIN_SITES", 6), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_SITES", 6), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MIN_SECONDS", 12), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_SECONDS", 12), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_CONCURRENT_TABS", 4), \
            mock.patch.object(adspower_extension_cleanup, "_warm_one_cookie_site", side_effect=fake_warm_site):
        result = await adspower_extension_cleanup.warm_ads_profile_cookies(
            _WarmupContext(),
            logger=None,
            profile_id="k1abc",
        )

    self.assertEqual(len(started), 6)
    self.assertEqual(len(result["visited"]), 6)
    self.assertLessEqual(max_active, 4)
    self.assertGreater(max_active, 1)
```

- [ ] **Step 2: Run the concurrency test and verify it fails**

Run: `python3 -m unittest tests.test_nyxify_cookie_warmup.CookieWarmupOrderingTests.test_cookie_warmup_runs_sites_with_concurrency_cap -v`

Expected: FAIL because the current implementation runs one warmup site at a time, so `max_active` is `1`.

### Task 2: Implement Capped Parallel Warmup

**Files:**
- Modify: `core/adspower_extension_cleanup.py`

- [ ] **Step 1: Add the concurrency env setting**

```python
COOKIE_WARMUP_MAX_CONCURRENT_TABS = max(1, _env_int("NYXIFY_COOKIE_WARMUP_MAX_CONCURRENT_TABS", 4))
```

- [ ] **Step 2: Replace the sequential loop with semaphore-backed workers**

```python
    concurrency = max(1, min(COOKIE_WARMUP_MAX_CONCURRENT_TABS, site_count))
    semaphore = asyncio.Semaphore(concurrency)

    async def visit_site(url):
        async with semaphore:
            try:
                ok = await _warm_one_cookie_site(context, url, seconds_per_site, logger, profile_id)
            except Exception as exc:
                if logger:
                    logger.warning(f"Cookie warm-up worker failed for {profile_id} at {url}: {exc}")
                return None
            return url if ok else None

    try:
        results = await asyncio.gather(*(visit_site(url) for url in selected_sites))
        visited = [url for url in results if url]
    finally:
        for page in list(getattr(context, "pages", []) or []):
            if page not in baseline_pages:
                await _safe_close_page(page)
```

- [ ] **Step 3: Run the concurrency test and verify it passes**

Run: `python3 -m unittest tests.test_nyxify_cookie_warmup.CookieWarmupOrderingTests.test_cookie_warmup_runs_sites_with_concurrency_cap -v`

Expected: PASS.

### Task 3: Add Cleanup And Failure Tests

**Files:**
- Modify: `tests/test_nyxify_cookie_warmup.py`

- [ ] **Step 1: Add a cleanup-before-return test**

```python
async def test_cookie_warmup_closes_pages_created_after_baseline(self):
    baseline_page = _WarmupPage("https://start.adspower.net/")
    context = _WarmupContext([baseline_page])

    async def fake_warm_site(context, url, _duration, _logger, _profile_id):
        page = await context.new_page()
        page.url = url
        return True

    with mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MIN_SITES", 3), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_SITES", 3), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_CONCURRENT_TABS", 3), \
            mock.patch.object(adspower_extension_cleanup, "_warm_one_cookie_site", side_effect=fake_warm_site):
        result = await adspower_extension_cleanup.warm_ads_profile_cookies(context, None, "k1abc")

    self.assertEqual(len(result["visited"]), 3)
    self.assertFalse(baseline_page.closed)
    warmup_pages = [page for page in context.pages if page is not baseline_page]
    self.assertEqual(len(warmup_pages), 3)
    self.assertTrue(all(page.closed for page in warmup_pages))
```

- [ ] **Step 2: Add a worker failure isolation test**

```python
async def test_cookie_warmup_worker_failure_does_not_stop_other_sites(self):
    calls = []

    async def fake_warm_site(_context, url, _duration, _logger, _profile_id):
        calls.append(url)
        if len(calls) == 2:
            raise RuntimeError("site exploded")
        return True

    with mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MIN_SITES", 4), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_SITES", 4), \
            mock.patch.object(adspower_extension_cleanup, "COOKIE_WARMUP_MAX_CONCURRENT_TABS", 4), \
            mock.patch.object(adspower_extension_cleanup, "_warm_one_cookie_site", side_effect=fake_warm_site):
        result = await adspower_extension_cleanup.warm_ads_profile_cookies(_WarmupContext(), None, "k1abc")

    self.assertEqual(len(calls), 4)
    self.assertEqual(len(result["visited"]), 3)
```

- [ ] **Step 3: Run the warmup test file**

Run: `python3 -m unittest tests.test_nyxify_cookie_warmup -v`

Expected: PASS.

### Task 4: Run Targeted Regression Tests

**Files:**
- Test: `tests/test_nyxify_cookie_warmup.py`
- Test: `tests/test_nyxify_continuous_mode.py`

- [ ] **Step 1: Run cookie warmup tests**

Run: `python3 -m unittest tests.test_nyxify_cookie_warmup -v`

Expected: PASS.

- [ ] **Step 2: Run Nyxify step-order regression**

Run: `python3 -m unittest tests.test_nyxify_continuous_mode.NyxifyContinuousModeTests.test_cookie_warmup_is_visible_step_before_signup_handoff -v`

Expected: PASS.
