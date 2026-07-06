# Changelog

## 6.0.2 — macOS search-click fix + signup stall recovery

- Fixes the Nyxify temp-name search on macOS ("Name contains &lt;temp&gt;") clicking beside the suggestion instead of on it. The dropdown row is now grouped by vertical-overlap ratio and the click lands on the field label itself, so it stays accurate across AdsPower window zoom levels and screen resolutions. The Nyx Profile-ID search is unchanged.
- Nyxify signup: when the page is stuck for a very long time and "Agree and Continue" never becomes clickable — even with a captcha present — the form is reloaded and re-filled from the saved credentials as a last resort.
- Nyxify signup: when the form is detected blank (for example after a manual page refresh), the saved credentials are re-entered immediately instead of waiting out the stall timer.

## 6.0.1 — AdsPower control mode selector

- Adds a dashboard Settings control for AdsPower mode: Auto, API, or GUI.
- GUI mode skips Local API create/open/close/delete/rename attempts and drives the AdsPower desktop app first, reducing cold-start delay on no-API accounts.
- API mode disables GUI/CDP fallback for devices where Local API-only behavior is preferred.
- Ships the AdsPower GUI template assets in the release ZIP for safer first-run setup on new devices.

## 6.0.0 — Public v6 source and release line

- Rebrands source-visible older line labels to v6.
- Uses the public `jaymaroldan026/nyxsuite-v6` repo for both source and dashboard update releases.
- Nyxify signup now uses each SnapBoard row's Password column, with the old default password retained only as a blank-row fallback.
- Keeps the no-API AdsPower GUI automation path for Windows and macOS.

## 5.0.0 — First no-API build

First public no-API release. Runs without the AdsPower Local API and
without any license/activation.

### No-API AdsPower automation (Windows)
When the AdsPower Local API is permission-gated (`9110 No local API permission`,
common on Employee/sub-accounts), the suite drives the AdsPower **desktop app**
directly instead of failing:

- **Create** profiles via the New-Profile form (name, group, proxy → Check Proxy → OK).
- **Open** profiles via the search bar, then attach Playwright over CDP.
- **Rename** profiles (Name edit-pencil) after a successful signup.
- **Close** profiles (row Close button) when a run finishes.
- **Delete** profiles (select → trash → confirm) on the signup retry path.
- Proxy pre-check falls back to a socket test when AdsPower's checker is gated.

The GUI automation is resolution-/DPI-/window-position-independent (Windows UI
Automation), with an OpenCV template-matching fallback. All GUI operations are
serialized across the Nyx and Nyxify processes by a cross-process lock.

### Other
- License/activation removed — runners start unconditionally.
- Cross-OS: installs and runs on Windows, macOS and Linux (Local API + Playwright);
  the no-API GUI fallback works on Windows and macOS.
- The Bitmoji and Snapchat-signup automation (Playwright) is unchanged.
