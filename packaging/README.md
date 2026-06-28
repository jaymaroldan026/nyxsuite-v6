# Nyx Suite Packaging (Windows)

Builds the Nyx Suite v4 bridge app (system tray + bundled `webui/` dashboard) plus
the two runner exes, and stamps the release with a sidecar `Updater.exe` that backs
the in-app "Check for Update" / rollback feature.

See [`V4_RELEASE.md`](V4_RELEASE.md) for the full release checklist (venv, license
secret, `.env`, and publishing to the releases repo).

## Scripts

- `build_updater.ps1` — builds `dist/Updater.exe` (the update/rollback sidecar).
- `build_bridge.ps1` — builds `bridge.spec`, `nyx_bot.spec`, and `nyxify_runner.spec`,
  then assembles `release/v4/NyxSuite <version>/` (bridge + both runners + `Updater.exe`
  + `update_config.json` + `VERSION`). Runs `build_updater.ps1` first unless `-SkipUpdater`.

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_bridge.ps1
```

## Requirements

- Windows
- AdsPower installed and running on the target machine
- A v4 venv at `venv\Scripts\python.exe` or `%LOCALAPPDATA%\NyxSuite\venv\Scripts\python.exe`,
  with `requirements.txt` + `PyInstaller` installed and the Playwright browser present
- The local license secret (`prepare_license_runtime_secret.ps1`, invoked automatically by the build)

## Release

Compress `release/v4/NyxSuite <version>/` to `NyxSuite-v<version>.zip` and publish it
to the releases repo (`nyxsuite-releases`). The `update_config.json` baked into the
build points the in-app updater at that repo.

## Scope

Windows packaging only. On macOS/Linux the suite runs from source via the portable
launchers (`run_nyx_suite.command` / `run_nyx_suite.sh`); a native macOS `.app`
build is not set up yet.
