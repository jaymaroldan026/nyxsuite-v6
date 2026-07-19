# Nyx Suite v6 Release Guide

Nyx Suite v6 uses a single public GitHub repository for source and update
assets: `jaymaroldan026/nyxsuite-v6`.

The dashboard updater reads `update_config.json`, calls GitHub Releases for that
repo, and downloads the newest non-draft release asset matching
`NyxSuite-v*.zip`.

## Latest Release Notes

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
