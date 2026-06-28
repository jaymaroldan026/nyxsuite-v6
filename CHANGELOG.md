# Changelog

## 5.0.0 — First release (no-API build)

First public release of Nyx Suite v5. Runs without the AdsPower Local API and
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
  the no-API GUI fallback is Windows-only.
- The Bitmoji and Snapchat-signup automation (Playwright) is unchanged.
