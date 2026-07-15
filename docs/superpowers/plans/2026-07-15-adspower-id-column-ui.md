# AdsPower ID Column UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AdsPower GUI automation resilient to the new Profiles table by using only the visible profile `ID` as row identity and ignoring optional chronology/order columns.

**Architecture:** Keep `core/adspower_ui.py` as the shared controller for Windows UIA and macOS AXUI. Add small row/header helpers that recognize `ID` and legacy `No./ID`, but never use `#`, date, platform, or order columns to identify a row. Preserve existing action controls for open, close, rename, delete, and checkbox selection.

**Tech Stack:** Python, unittest/pytest, pywinauto on Windows, AXUIElement/PyObjC on macOS, pyautogui for physical input.

---

### Task 1: Row Layout Regression Tests

**Files:**
- Modify: `tests/test_adspower_open_batch.py`

- [ ] **Step 1: Write failing tests**

Add tests for `_scan_rows`, `_row_center_y`, `_batch_action_snapshot`, and missing visible ID behavior using `_FakeWindow`, `_FakeControl`, and `_Rect`.

Required cases:

```python
def test_scan_rows_supports_new_separate_id_and_order_columns(self):
    win = _FakeWindow(
        texts=[
            _FakeControl("ID", _Rect(90, 170, 150, 194)),
            _FakeControl("Group", _Rect(220, 170, 290, 194)),
            _FakeControl("Name", _Rect(360, 170, 430, 194)),
            _FakeControl("IP", _Rect(520, 170, 590, 194)),
            _FakeControl("#", _Rect(700, 170, 730, 194)),
            _FakeControl("k1target", _Rect(90, 232, 155, 252)),
            _FakeControl("Snapchat19", _Rect(220, 230, 300, 252)),
            _FakeControl("Snapchat: Olivia", _Rect(360, 230, 470, 252)),
            _FakeControl("78.105.159.107", _Rect(520, 230, 620, 252)),
            _FakeControl("1", _Rect(700, 230, 715, 252)),
        ]
    )
    ctrl = self._controller(win)
    self.assertEqual(ctrl._scan_rows(), [(0, "k1target", "Snapchat: Olivia")])
```

Also add a test where `#` appears before `ID`, and another where the row has no visible `ID` text and `_ensure_row_visible("k1target")` returns `False` after a search.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adspower_open_batch.py::RowActionClickTests -q`

Expected: FAIL because production scanning still pairs serial/order numbers with IDs and does not yet have the new visible-ID-only logic.

### Task 2: Shared Row Snapshot Helpers

**Files:**
- Modify: `core/adspower_ui.py`

- [ ] **Step 1: Implement minimal helpers**

Add header constants and helpers in `AdsPowerUIController`:

```python
_ROW_ID_HEADERS = {"id", "no./id"}
_ROW_DATA_HEADERS = {"id", "no./id", "group", "name", "ip", "action"}
_IGNORED_ROW_HEADERS = {"#", "no.", "last opened", "date created", "platform", "tags", "custom no."}
```

Add a helper that returns visible text controls as `(text, rect)` while skipping hidden/zero-size controls, and a helper that detects the list header bottom from `ID`, `Group`, `Name`, `IP`, or `Action`.

- [ ] **Step 2: Update `_scan_rows`**

Rewrite `_scan_rows` so profile IDs are row anchors. For each visible text matching `_PROFILE_ID_RE`, find the closest same-band `Name` text that starts with `Snapchat:` and return `(0, profile_id, name)`. Keep legacy `No./ID` support by also accepting old rows where numeric No. and ID share one cell/column, but do not require or trust the numeric value.

- [ ] **Step 3: Update row/action helpers**

Update `_list_header_bottom`, `_row_action_snapshot`, `_batch_action_snapshot`, `_row_center_y`, `_row_id_rect`, `_row_checkbox_rect`, and row-menu alignment to use the exact visible profile ID row. Header detection must include `ID`, `Group`, `Name`, `IP`, and `Action`.

- [ ] **Step 4: Add missing-ID error text**

When a target row cannot be proven after a `Profile ID is <id>` search, raise `AdsPowerProfileNotFoundError` with guidance to enable the `ID` column in AdsPower List Settings.

### Task 3: Verify Focused Tests

**Files:**
- Test only.

- [ ] **Step 1: Run focused unit tests**

Run: `.venv/bin/python -m pytest tests/test_adspower_open_batch.py tests/test_adspower_macos_backend.py tests/test_adspower_dropdown_click_target.py -q`

Expected: PASS.

- [ ] **Step 2: Run broader AdsPower tests**

Run: `.venv/bin/python -m pytest tests/test_adspower_control_mode.py tests/test_dashboard_adspower_control_mode.py tests/test_adspower_cdp_fallback.py tests/test_adspower_delete.py -q`

Expected: PASS.

### Task 4: Release Update

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`
- Modify: `RELEASE.md`
- Modify: `update_config.json`

- [ ] **Step 1: Bump version**

Use the existing version-sync tooling or established metadata pattern to bump from the current version to the next patch release.

- [ ] **Step 2: Document release**

Add a changelog/release note that says AdsPower GUI control now supports the new separate `ID` column layout on Windows and macOS, ignores optional/reordered columns, and reports a clear error when `ID` is hidden.

- [ ] **Step 3: Run release metadata tests**

Run: `.venv/bin/python -m pytest tests/test_release_packaging.py tests/test_rollback_versions.py -q`

Expected: PASS.

- [ ] **Step 4: Commit, push, and create release**

Stage only files touched for this change, commit, push to GitHub, and create/publish the release using the repo's existing release process.
