# macOS AdsPower AXUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add macOS Silicon AXUIElement support to the existing no-API AdsPower GUI automation without regressing Windows.

**Architecture:** Keep AdsPower lifecycle behavior in `core/adspower_ui.py` and introduce platform backends that provide a pywinauto-compatible control/window/input surface. Windows keeps pywinauto/Win32 behavior; macOS uses PyObjC AXUIElement, AppKit focus, file locking, clipboard, and pyautogui.

**Tech Stack:** Python, unittest, PyObjC ApplicationServices/Quartz/Cocoa, pyautogui, pywinauto on Windows, AdsPower desktop, Playwright CDP.

---

### Task 1: Backend Selection And macOS Dependency Gate

**Files:**
- Modify: `requirements.txt`
- Modify: `core/adspower_ui.py`
- Test: `tests/test_adspower_macos_backend.py`

- [ ] **Step 1: Write failing backend-selection tests**

Create tests that assert macOS can select a backend when PyObjC is present and that missing Accessibility permission raises an actionable error.

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `python3 -m unittest tests.test_adspower_macos_backend -v`
Expected: FAIL because the backend module does not exist.

- [ ] **Step 3: Add macOS-only requirements**

Add PyObjC, pyautogui, opencv-python, and numpy with `sys_platform == "darwin"` markers.

- [ ] **Step 4: Add backend selection**

Update `AdsPowerUIController` construction to select Windows pywinauto on Windows and macOS AXUIElement on Darwin.

- [ ] **Step 5: Run targeted tests and verify GREEN**

Run: `python3 -m unittest tests.test_adspower_macos_backend -v`
Expected: PASS.

### Task 2: macOS AXUIElement Backend

**Files:**
- Create: `core/adspower_ui_backend_macos.py`
- Modify: `core/adspower_ui.py`
- Test: `tests/test_adspower_macos_backend.py`

- [ ] **Step 1: Write failing adapter tests**

Test role mapping, text extraction, rectangle conversion, visibility, child lookup, descendant traversal, and invoke fallback.

- [ ] **Step 2: Run and verify RED**

Run: `python3 -m unittest tests.test_adspower_macos_backend -v`
Expected: FAIL because wrappers are missing.

- [ ] **Step 3: Implement minimal AX wrappers**

Expose `window_text()`, `rectangle()`, `is_visible()`, `descendants(control_type)`, `child_window(title, control_type)`, `exists(timeout)`, and `invoke()`.

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run: `python3 -m unittest tests.test_adspower_macos_backend -v`
Expected: PASS.

### Task 3: Live macOS Smoke Harness

**Files:**
- Modify: `tools/test_adspower_ui_profile.py`
- Modify: `README.md`

- [ ] **Step 1: Add a macOS dependency/permission preflight to the smoke tool**

The tool should show a clear message if PyObjC or Accessibility permission is missing.

- [ ] **Step 2: Run unit tests**

Run: `python3 -m unittest tests.test_adspower_macos_backend tests.test_adspower_open_batch tests.test_adspower_cdp_fallback -v`
Expected: PASS.

- [ ] **Step 3: Run live lifecycle**

Run: `python3 tools/test_adspower_ui_profile.py --lifecycle`
Expected: creates the default temp profile, opens it, resolves CDP, closes it, deletes it.

- [ ] **Step 4: Iterate from live failures using root-cause evidence**

Use AX tree dumps and targeted logging to fix element role/name mismatches until the lifecycle works.
