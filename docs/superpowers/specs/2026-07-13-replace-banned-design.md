# Replace Banned Design

## Goal
Add a Nyxify Replace Banned workflow that scans SnapBoard for banned rows and immediately replaces each banned account by deleting the old AdsPower profile, refreshing row credentials/proxy, setting Warm Up, and requeueing the row in Nyxify.

## Scope
- Add Replace Banned to the Nyxify extension popup.
- Add Replace Banned to the Nyxify web dashboard.
- Update the Nyx extension SnapBoard dot menu:
  - Replace profile uses the same replacement flow and does not ask for confirmation.
  - Add to Nyx pending queues that row/profile in Nyx without confirmation.
- Remove Clear Queue from the Nyx dashboard.
- Compact the Nyx and Nyxify dashboard command header so more table space is visible.
- Bump the release version and changelog after verification.

## Architecture
SnapBoard row scanning remains in the extension content script because only the content script can inspect the SnapBoard table DOM. The Nyxify local API owns replace orchestration because it already owns the bridge stores for username, email, proxy, status, and AdsPower ID updates.

The Nyxify content script reports full SnapBoard row snapshots, including status and rows that still have AdsPower IDs. The Nyxify local API stores the latest snapshot and exposes scan/replace endpoints to the popup and dashboard.

Replacement is row-by-row:
- Delete/close the old AdsPower profile through the Nyxify controller's AdsPower manager.
- Clear the SnapBoard AdsPower ID through the existing AdsPower update bridge.
- Rotate the SnapBoard proxy through the existing proxy bridge.
- Reserve a fresh Full Auto username and write it to SnapBoard through the existing username bridge.
- Request a fresh email through the existing email bridge.
- Set SnapBoard status to Warm Up through the existing status bridge.
- Reset/upsert the Nyxify task to PENDING with old AdsPower fields cleared and the fresh username/email/proxy stored.

## UI
Nyxify popup gets a small Replace Banned panel with Scan banned, Replace all banned, and a concise result line. The dashboard gets the same controls in the Nyxify command header, with a count/result summary.

The web dashboard header becomes a two-zone command layout: runner status and count tiles on the left, compact actions/config/search on the right. Controls remain visible, but the table starts higher and has more horizontal room.

## Error Handling
Each row returns a success, partial, or failed result. A delete failure stops that row before clearing SnapBoard fields. Username/email/proxy/status bridge failures are reported per row; rows with enough fresh data are still reset to PENDING so Nyxify can retry normal processing.

## Testing
- Add task-store tests for replacement reset semantics.
- Add content/background string-level bridge tests for Scan Banned and Replace Banned wiring.
- Add dashboard string-level tests for the new dashboard controls and removal of Nyx Clear Queue.
- Run focused tests, then a broader relevant suite before commit.
