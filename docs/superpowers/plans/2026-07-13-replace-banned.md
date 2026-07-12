# Replace Banned Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Replace Banned across Nyxify popup, web dashboard, and Nyx SnapBoard menu, then ship it as a versioned release update.

**Architecture:** SnapBoard scanning lives in content scripts. Nyxify local API stores scan snapshots and orchestrates replace operations through existing bridge stores. Dashboard and popup call the same scan/replace endpoints.

**Tech Stack:** Python `http.server`, SQLite task store, vanilla Chrome extension JavaScript, vanilla web dashboard JavaScript/CSS, pytest/unittest.

---

### Task 1: Replacement Task Store Semantics

**Files:**
- Modify: `core/nyxify_task_store.py`
- Test: `tests/test_nyxify_snapboard_bridge.py`

- [x] Write a failing test that a replacement reset clears old AdsPower fields and returns a PENDING row with fresh username/email/proxy.
- [x] Run `pytest tests/test_nyxify_snapboard_bridge.py::NyxifySnapboardBridgeTests::test_replace_banned_reset_clears_old_adspower_fields -q` and confirm it fails because the method is missing.
- [x] Implement `replace_for_banned_account(...)` in `NyxifyTaskStore`.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Nyxify Replace Banned API

**Files:**
- Modify: `core/nyxify_local_api.py`
- Modify: `core/nyxify_controller.py`
- Test: `tests/test_nyxify_snapboard_bridge.py`

- [x] Write failing tests that assert the API source contains scan snapshot and replace endpoints plus a controller delete handler.
- [x] Implement latest SnapBoard snapshot storage and `/replace_banned/snapshot`, `/replace_banned/scan`, `/replace_banned/replace`.
- [x] Add Nyxify controller `delete_adspower_profile` action.
- [x] Re-run the focused bridge tests.

### Task 3: Extension Bridge And Menus

**Files:**
- Modify: `nyxify_extension/content.js`
- Modify: `nyxify_extension/background.js`
- Modify: `nyxify_extension/popup.html`
- Modify: `nyxify_extension/popup.js`
- Modify: `nyxify_extension/styles.css`
- Modify: `nyx_extension/content.js`
- Modify: `nyx_extension/background.js`
- Test: `tests/test_nyxify_snapboard_bridge.py`

- [x] Write failing string-level tests for SnapBoard banned-row scan, Nyxify popup controls, Nyx manual replace delegation, and Add to Nyx pending.
- [x] Implement row status extraction and banned scan responses in Nyxify content.
- [x] Implement background handlers to publish snapshots, scan active SnapBoard, and call replace.
- [x] Add popup controls and result rendering.
- [x] Update Nyx content dot menu to remove confirm and add Add to Nyx pending.
- [x] Add Nyx background handlers for replacement and Nyx pending upsert.
- [x] Re-run focused tests.

### Task 4: Dashboard Compact Header And Controls

**Files:**
- Modify: `webui/index.html`
- Modify: `webui/dashboard.js`
- Modify: `webui/dashboard.css`
- Test: `tests/test_dashboard_adspower_control_mode.py` or a new focused dashboard source test

- [x] Write failing tests for Nyx Clear Queue removal and Replace Banned dashboard controls.
- [x] Remove Nyx Clear Queue from dashboard queue actions.
- [x] Add Nyxify dashboard scan/replace controls.
- [x] Refactor panel layout into compact command header.
- [x] Re-run focused dashboard tests.

### Task 5: Release Update And Verification

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`

- [x] Bump `VERSION` from `6.1.6` to `6.1.7`.
- [x] Add `6.1.7` changelog entry for Replace Banned and dashboard compaction.
- [x] Run focused tests.
- [x] Run a broader relevant unittest subset.
- [x] Stage only intended files.
- [x] Commit with a release message.
- [x] Push `master` to `origin`.
