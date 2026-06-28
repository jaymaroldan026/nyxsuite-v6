# Nyx Suite (v4) — build & release

> **Current version: 4.1.0** — see `core/version.py` (single source of truth).

## v4.1 changes

### New components
- `agent_host/host_main.py` — native-messaging host launcher (ping, connect, start_agent, get_token, agent_status)
- `agent_host/com.nyxsuite.agent.json` — native-messaging manifest (must be registered per-OS)
- `agent_host/install_host.py` — cross-platform host registration/unregistration (`--register` / `--unregister`)
- `core/startup.py` — cross-platform run-on-login (Windows HKCU Run, macOS LaunchAgents, Linux XDG autostart)

### Extension changes (both nyx_extension + nyxify_extension)
- `manifest.json` — v4.1.0, added `"key"` (stable extension ID), `"nativeMessaging"` permission, title updated to `"Nyx v4"` / `"Nyxify v4"`
- `popup.html` — added agent-row with "Open Web App" + "Connect to Agent" buttons
- `styles.css` — added agent-row / button-group styles
- `popup.js` — added native-messaging connection handlers (`openWebApp`, `connectToAgent`)
- `background.js` — default `localApiUrl` changed from `:8765` → `:8865` (Nyx) / `:8766` → `:8866` (Nyxify)

### Web dashboard changes
- `index.html` — rewritten with 4-tab layout: Nyx, Nyxify, Full Auto (editor), Settings (license/updates/autostart/config)
- `dashboard.js` — v4.1 full rewrite: SSE real-time, Settings page (license activate, check update / apply / rollback, autostart toggle, advanced config editor), Full Auto editor (model selector, load/save usernames + signup names)
- `dashboard.css` — new panel styles (Settings grid, toggle switches, Full Auto grid with textareas, responsive layout)

### Backend changes
- `bridge_app.py` — added bridge actions: `license_status`, `license_request_code`, `license_activate`, `autostart`, `set_autostart`
- `core/nyxify_local_api.py` — added Full-Auto endpoints: `GET /models`, `GET /usernames`, `POST /usernames`, `GET /signup_names`, `POST /signup_names`
- `core/webui_server.py` — `_inject_token()` injects `window.__NYX_TOKEN__` into `index.html`; CORS allowlist for dashboard + extension origins; SSE token auth via `?token=` query param
- `core/version.py` — bumped from 4.0.0 → 4.1.0
- `scripts/sync_version.py` — removed retired `extension/` target

### Security
- Per-install token enforced on all POST endpoints and SSE/status GET (via `?token=` for EventSource, headers for fetch)
- Token distributed: injected into web dashboard (`window.__NYX_TOKEN__`), handed to extension via Connect handshake
- CORS allowlist: dashboard origin + extension origins (chrome-extension://, moz-extension://)

### Registration flow (one-time)
```powershell
# Register the native-messaging host (admin on Windows, sudo on macOS/Linux)
py agent_host/install_host.py --register

# Enable autostart (optional, also available via Web UI Settings)
py -c "from core.startup import set_start_on_login; set_start_on_login(True)"
```



The v4 line ships as a **separate product** from v3: its own source repo, its own
GitHub **releases repo**, its own install (`%LOCALAPPDATA%/NyxSuite`) and port block
(88xx), so the existing v3 install can never be touched or auto-updated by v4.

Everything below runs on **Windows** (PyInstaller + the runners' Playwright Chromium).
These scripts were authored from the v3 build pattern — verify the first build.

## One-time dev/build setup
1. Create the v4 venv and install deps:
   - `py -3 -m venv venv`
   - `venv\Scripts\python -m pip install -r requirements.txt`
   - `venv\Scripts\python -m playwright install chromium`   (runners need it)
2. Copy the local-only secrets into this checkout (git-ignored, never committed):
   - `core\license_runtime_secret.py`  (from the v3 checkout / your secret store)
   - `.env`  (your AdsPower `ADSP_*` values)

## Build
```
powershell -ExecutionPolicy Bypass -File packaging\build_bridge.ps1
```
This builds `bridge.spec` (→ `NyxSuite v4.0.0.exe`, with `webui/` bundled),
`nyx_bot.spec` (→ `NyxBot v4.0.0.exe`) and `nyxify_runner.spec`
(→ `NyxifyRunner v4.0.0.exe`), builds `Updater.exe`, and assembles
`release\v4\NyxSuite v4.0.0\` with `webui/`, `VERSION`, `update_config.json`
(pointing at the v4 releases repo) and `start_suite.bat`.

## GitHub repos (create once)
- **Source (PRIVATE):** `snap_bitmoji_bot_v4` — it carries `tools/generate_activation_code.py`,
  which must never be public. Push this checkout's `feature/web-ui-bridge` branch.
- **Releases (PUBLIC):** `nyxsuite-releases` — so the in-app updater can
  fetch without auth. The name must match `repo` in the generated `update_config.json`
  (and in `core/update_backup.py` rollback flows, which reuse the bundled config).

## Publish a TEST release
1. Compress `release\v4\NyxSuite v4.0.0\` → `NyxSuite-v4.0.0.zip` (single top-level folder inside).
2. Create a GitHub release on `nyxsuite-releases`, tag `v4.1.0`, **mark it a pre-release**,
   and upload the zip.
3. The v3 line is untouched — v3 apps keep pulling from `snap_bitmoji_bot_releases`.

## Verify on a test machine
- Install: unzip, run `start_suite.bat` → tray + dashboard at `http://127.0.0.1:8870/`.
- Coexistence: a v3 install can run at the same time (different data dir + 87xx ports).
- Update + rollback: from an older v4 build, **Check for Update** → apply → confirm
  `local_update_backups\<prev>\` is created and the app relaunches on the new version,
  then **Roll back to previous** restores it. Corrupt the new exe to confirm the
  launch watchdog auto-rolls back after repeated failed starts.

## Rolling a new version
Bump `core/version.py` (single source of truth → exe names, titles, VERSION,
extension manifests via `scripts/sync_version.py`), rebuild, zip as
`NyxSuite-v<new>.zip`, publish. Keep the previous release published as a rollback target.
