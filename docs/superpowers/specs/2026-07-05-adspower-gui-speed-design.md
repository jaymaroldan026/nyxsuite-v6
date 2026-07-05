# AdsPower GUI Speed Design

## Goal

Optimize AdsPower GUI automation speed and accuracy on Windows and macOS without removing or changing the AdsPower Local API path.

## Scope

The AdsPower API code remains available. This change targets no-API GUI automation only: create, open, rename, close, and delete actions in `core/adspower_ui.py`, plus the macOS accessibility adapter in `core/adspower_ui_backend_macos.py`.

## Design

GUI actions must remain resolution-, app-size-, placement-, DPI-, and theme-independent. The implementation will continue to use platform accessibility controls and real control rectangles as the primary source of truth. Coordinate clicks are allowed only when derived from verified row/control geometry, such as a row's visible profile ID rectangle.

The speed improvement comes from removing unnecessary fixed waits. After clicks and pastes, the controller should poll for the next expected state and continue as soon as it is visible: form open, form closed, proxy parser populated, proxy result text, row button changed, row disappeared, or CDP endpoint appeared.

On macOS, reconnecting to the accessibility tree must not reactivate AdsPower and sleep on every lookup. The backend should reuse the current accessible AdsPower window while it remains valid, clear per-read attribute cache between snapshots, and only foreground the app when it is not already frontmost or an action needs real input.

## Testing

Unit tests will cover the timing contracts without driving the real GUI: macOS backend reconnect reuse, shorter macOS raw paste pacing, and condition-based proxy-check polling. Live verification will run through `tools/test_adspower_ui_profile.py --name "Snapchat: xoxoxo" --lifecycle` using the repo venv.

## Non-Goals

No AdsPower API removal. No hard-coded screen coordinates. No theme-specific image-only automation. No dependency on a fixed AdsPower window size or position.
