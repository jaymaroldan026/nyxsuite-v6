# Nyx Suite v6 Release Guide

Nyx Suite v6 uses a single public GitHub repository for source and update
assets: `jaymaroldan026/nyxsuite-v6`.

The dashboard updater reads `update_config.json`, calls GitHub Releases for that
repo, and downloads the newest non-draft release asset matching
`NyxSuite-v*.zip`.

## Latest Release Notes

### NyxSuite v6.1.14

- Nyx whole-profile retries now also catch transient AdsPower/CDP open
  exceptions, including delayed DevTools endpoints, target-closed races, and
  Bitmoji editor load exceptions.
- Permanent profile/config errors still fail immediately instead of burning
  retries.
- Nyxify account creation now sends OTP, SnapBoard handoff, and submitted-signup
  stalls through the existing cleanup/retry path: close/delete the created
  AdsPower profile, clear the SnapBoard AdsPower ID, optionally rotate proxy,
  and requeue the row as pending.

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
