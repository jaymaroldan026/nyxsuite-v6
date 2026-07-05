# AdsPower GUI Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AdsPower GUI automation react faster when controls are already visible while preserving cross-resolution and cross-theme accuracy.

**Architecture:** Keep `core/adspower_ui.py` as the shared controller and `core/adspower_ui_backend_macos.py` as the macOS accessibility adapter. Replace fixed sleeps with bounded polling for verified accessibility state. Keep clicks anchored to UIA/AX rectangles or row geometry derived from visible profile IDs.

**Tech Stack:** Python, unittest, pywinauto on Windows, AXUIElement/PyObjC on macOS, pyautogui for real input, Playwright CDP for live profile attach.

---

### Task 1: Timing Contract Tests

**Files:**
- Modify: `tests/test_adspower_open_batch.py`
- Modify: `tests/test_adspower_macos_backend.py`

- [ ] **Step 1: Write failing tests**

Add tests that expect macOS raw paste to use short pacing, proxy check polling to inspect visible text before sleeping, and macOS backend reconnect to reuse a valid cached window without foregrounding every snapshot.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adspower_open_batch.py::ProxyFillTests::test_macos_raw_paste_uses_short_condition_friendly_settle tests/test_adspower_open_batch.py::ProxyCheckSpeedTests::test_check_proxy_reads_visible_result_before_sleeping tests/test_adspower_macos_backend.py::MacBackendConnectionSpeedTests::test_connect_reuses_valid_cached_window_without_foreground_sleep -q`

Expected: FAIL because the production code still uses long macOS paste waits, sleeps before proxy result reads, and reconnects/foregrounds on every macOS connect.

### Task 2: MacOS Accessibility Reconnect

**Files:**
- Modify: `core/adspower_ui_backend_macos.py`

- [ ] **Step 1: Implement cached-window reconnect**

Add a cached-window fast path to `MacOSAdsPowerBackend.connect()`. It should clear `_attr_cache`, reuse `_window` when its rectangle is large enough to be a real window, and skip foregrounding when AdsPower is already frontmost.

- [ ] **Step 2: Run macOS backend test**

Run: `.venv/bin/python -m pytest tests/test_adspower_macos_backend.py::MacBackendConnectionSpeedTests::test_connect_reuses_valid_cached_window_without_foreground_sleep -q`

Expected: PASS.

### Task 3: Shared GUI Wait Tuning

**Files:**
- Modify: `core/adspower_ui.py`

- [ ] **Step 1: Implement condition-driven waits**

Add small config knobs for polling intervals and macOS paste settle. Update `_paste_rect`, `_open_new_profile_form`, `_check_proxy`, `_find`, and `_rect` so visible state short-circuits waits. Preserve all accessibility-rectangle targeting.

- [ ] **Step 2: Run timing tests**

Run: `.venv/bin/python -m pytest tests/test_adspower_open_batch.py::ProxyFillTests::test_macos_raw_paste_uses_short_condition_friendly_settle tests/test_adspower_open_batch.py::ProxyCheckSpeedTests::test_check_proxy_reads_visible_result_before_sleeping -q`

Expected: PASS.

### Task 4: Regression Suite

**Files:**
- Test only.

- [ ] **Step 1: Run focused regression tests**

Run: `.venv/bin/python -m pytest tests/test_adspower_open_batch.py tests/test_adspower_macos_backend.py tests/test_adspower_cdp_fallback.py -q`

Expected: PASS.

- [ ] **Step 2: Run live AdsPower GUI lifecycle**

Run: `.venv/bin/python tools/test_adspower_ui_profile.py --name "Snapchat: xoxoxo" --lifecycle`

Expected: exits 0 after creating, opening, closing, and deleting the temporary `Snapchat: xoxoxo` profile.
