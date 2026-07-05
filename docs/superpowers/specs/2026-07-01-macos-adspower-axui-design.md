# macOS AdsPower AXUI No-API Design

## Goal

Add macOS Silicon support to the no-API AdsPower GUI automation while preserving the same high-level behavior that already works on Windows: create profiles, resolve IDs, open profiles, attach over CDP, rename, close, and delete.

## Approved Approach

Use option 1: keep the high-level `AdsPowerUIController` behavior shared and place OS-specific window, accessibility, input, clipboard, and lock behavior behind platform adapters.

## Architecture

`core/adspower_ui.py` remains the owner of AdsPower workflow semantics: temp-name filtering, row scanning, bulk ID search, bulk open/close, rename, delete, and CDP resolution. It chooses a backend at runtime. Windows continues to use pywinauto and Win32 APIs. macOS uses PyObjC to read the Accessibility AXUIElement tree for AdsPower Global and uses `pyautogui` plus the clipboard for user input.

The backend must expose a pywinauto-like surface to reduce churn in the existing row/search logic: `child_window`, `descendants`, `rectangle`, `window_text`, `is_visible`, and optional `invoke`.

## macOS Behavior

The macOS backend finds the AdsPower Global process, locates the visible AdsPower Browser / AdsPower Global window, raises it through AppKit, reads controls through AXUIElement attributes, and maps macOS AX roles to the existing control types used by the controller. It uses a file lock under the user temp directory for cross-process serialization, matching the Windows named mutex intent.

If macOS Accessibility permission is missing, construction fails with an actionable error telling the user to grant Accessibility permission to Terminal, Codex, or the bundled Nyx Suite app.

## Dependencies

Add macOS-only dependencies:

- `pyobjc-framework-ApplicationServices`
- `pyobjc-framework-Quartz`
- `pyobjc-framework-Cocoa`
- `pyautogui`
- `opencv-python` and `numpy` for the existing vision fallback on macOS

## Testing

Follow test-first implementation:

1. Add unit tests for backend selection and pywinauto-compatible fake controls.
2. Verify the new tests fail before implementation.
3. Implement the backend and minimal controller changes.
4. Run targeted unit tests.
5. Run the live default lifecycle test on this device:
   `python tools/test_adspower_ui_profile.py --lifecycle`
6. Iterate until the live AdsPower GUI flow works or a real OS permission blocker is reached.
