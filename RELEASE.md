# Nyx Suite v6 Release Guide

Nyx Suite v6 uses a single public GitHub repository for source and update
assets: `jaymaroldan026/nyxsuite-v6`.

The dashboard updater reads `update_config.json`, calls GitHub Releases for that
repo, and downloads the newest non-draft release asset matching
`NyxSuite-v*.zip`.

## Latest Release Notes

### NyxSuite v6.2.9

- Continuous Mode now prioritizes an active Snapchat `Continue to Bitmoji?`
  OAuth consent tab over older login tabs, so immediate Nyxify handoffs proceed
  into Bitmoji automation instead of parking at `need_login`.
- Nyx scans every CDP browser context for OAuth/editor progress states before
  falling back to Snapchat login detection.
- AdsPower GUI rename now retries by reapplying Nyxify's remembered temp-name
  filter when the profile row is not visible under the current AdsPower search.

### NyxSuite v6.2.8

- Fixed the Continuous Mode Bitmoji auth stall shown as `need_login` while the
  browser is already on Snapchat's `Continue to Bitmoji?` OAuth consent page.
- Snapchat OAuth consent pages now take priority over login-page detection, even
  when the page contains hidden username/password fields.
- Nyx now routes that screen straight into the OAuth Continue click path so the
  Bitmoji editor automation can proceed without manual intervention.

### NyxSuite v6.2.7

- Continuous Mode Nyx handoff no longer gets stuck at `need_login` when the
  Snapchat login page advances into Bitmoji OAuth before the login form appears.
- Nyx now recognizes OAuth/Bitmoji handoff states while waiting for Snapchat
  auto-login fields, so it proceeds to Continue/Gender/Editor instead of
  falling into manual-login wait.
- `need_login` is now recorded only after automatic Snapchat login has actually
  failed and Nyx is entering manual-login wait.

### NyxSuite v6.2.6

- Continuous Mode now runs as a one-account pipeline: Nyxify creates the
  Snapchat account, renames the AdsPower profile, hands it to Nyx immediately,
  then waits for that continuous Nyx work before starting the next signup.
- Nyx queue handoff now uses a high-priority `run_now` path so continuous
  Bitmoji tasks are selected ahead of normal pending rows as soon as a Nyx slot
  is available.
- Nyxify now shows `waiting_for_continuous_nyx` while a continuous Nyx handoff
  is pending or running, reducing accidental overlap without blocking manual
  Stop/Restart controls.

### NyxSuite v6.2.5

- AdsPower profile close now first targets the profile's own Chromium CDP
  endpoint and closes every tab, avoiding another AdsPower GUI search when the
  browser can close itself.
- The CDP close path bypasses page "Leave site?" prompts by closing tabs without
  running before-unload handlers.
- Existing AdsPower API and GUI close paths remain as fallbacks when a profile
  does not have a live CDP endpoint.

### NyxSuite v6.2.4

- Windows launcher now starts from its own install folder, preserves failures,
  and pauses when setup fails so the operator can read the error.
- Windows PowerShell launch now quotes the bridge entry-script path, fixing
  installs whose folder path contains spaces.
- The source updater now skips empty staged source directories, preventing an
  empty release folder from wiping installed bridge/native-host files.
- Proxy Ranking's "Ban all red proxies" now refreshes live ranking rows before
  posting the ban, and explicit ban actions turn Proxy Blocker enforcement on.

### NyxSuite v6.2.3

- Nyxify now detects Snapchat wrong-code verification errors and recovers by
  going back, requesting a fresh SnapBoard email or phone number, and retrying
  the new code on the same signup.
- The SnapBoard banned-row scan controls no longer show the initial
  "Scan SnapBoard for banned rows." helper text in the dashboard or popup.
- Proxy Ranking now surfaces the worst subnets first, adds Good/Watch/Red
  summary chips, highlights red rows, and adds a bulk "Ban all red proxies"
  action.

### NyxSuite v6.2.2

- Nyxify signup recovery now refreshes faster: no-captcha/signup stalls after
  100 seconds and hard stuck signup pages after 200 seconds.
- Nyxify now refreshes and re-enters signup details when the expected signup
  form or verification handoff page is not detected for the stall window.
- Added regression coverage for the new signup refresh timings and missing-page
  recovery path.

### NyxSuite v6.2.1

- AdsPower GUI recovery now hard-refreshes the desktop app when the dashboard
  becomes unresponsive: Shift-Command-R on macOS and Control-Shift-R on Windows,
  after foregrounding AdsPower.
- Nyxify signup refresh/retry coverage now explicitly protects the filled-form
  no-captcha stall path, along with the existing reCAPTCHA unreachable and
  blank-form refill recovery paths.
- Nyx now keeps a private copy of the SnapBoard Snapchat username/password on
  the Nyx queue row, so Bitmoji auto-login still uses the real account password
  even after the Nyxify row is pruned, replaced, or no longer matches.
- Nyx and Nyxify handoff paths now carry SnapBoard credentials through the
  extension, local API, direct fallback queue write, and continuous-mode handoff.

### NyxSuite v6.2.0

- Dashboard command areas now use consistent zones for Nyx and Nyxify: runner
  controls, product tools, queue actions, selected-row actions, search, and
  Nyxify-only banned-row utilities.
- Queue buttons and row buttons keep the same placement across both dashboard
  tabs, with responsive wrapping that avoids horizontal overflow.
- Nyxify extension popup now places Start/Stop and Pause/Resume at the top of
  the runner card, above the counters, with a compact runner-state pill.
- Pause starts disabled and only becomes available when the Nyxify runner is
  active.
- Nyx and Nyxify popup headers are smaller to free up control space.
- Nyxify popup hides Push AdsPower ID and Apply AdsPower tags, moves Auto-Fill
  Row/target to the top of the toggle panel, and keeps the hidden settings wired
  through backend/options config.
- Both extension popups now auto-save dashboard settings as fields are typed or
  changed, so the manual Save Dashboard Settings button is gone.

## Create a New Release

1. Update the version in `core/version.py`.
2. Run:

   ```bash
   python scripts/sync_version.py
   ```

3. Build the source update ZIP.

   macOS/Linux:

   ```bash
   bash packaging/create_release_zip.sh --version <version>
   ```

   Windows:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\packaging\create_release_zip.ps1 -Version <version>
   ```

4. Confirm the ZIP contains one top-level folder named `NyxSuite-v<version>/`.
5. Create the release and upload the asset:

   ```bash
   gh release create v<version> dist/NyxSuite-v<version>.zip \
     --repo jaymaroldan026/nyxsuite-v6 \
     --title "NyxSuite v<version>" \
     --notes "Describe the user-facing changes."
   ```

6. Verify update from an older install:
   - Windows: Dashboard -> Settings -> Check for Update -> Apply Update.
   - macOS: run `run_nyx_suite.command`, then Dashboard -> Settings -> Check for Update -> Apply Update.

## Update Package Rules

- Keep `update_config.json` pointed at `jaymaroldan026/nyxsuite-v6`.
- Keep `asset_pattern` as `NyxSuite-v*.zip`.
- Do not ship runtime databases, local `.env`, logs, local update backups, or license/signing secrets.
- The release ZIP preserves runtime DB/config/log paths during update.
- The native-messaging manifest in the ZIP must use `agent_host/host_main.py`, not a machine-specific absolute path.

## SnapBoard Password Behavior

Nyxify reads the SnapBoard Password column from each row and uses it when filling
the Snapchat signup form. If the row password is blank, signup falls back to the
legacy default password `ABC123wgmi*`.
