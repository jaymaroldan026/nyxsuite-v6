# AdsPower ID Column UI Design

## Goal

Update the no-API AdsPower GUI automation so it works with the new AdsPower Profiles table on Windows and macOS. The new UI separates the AdsPower profile `ID` from optional order columns such as `#` and lets operators reorder or hide columns.

## Approved Behavior

The automation treats only these visible table fields as meaningful row data:

- `ID`
- `Group`
- `Name`
- `IP`

All other visible columns are ignored for row identity and action targeting. This includes `#`, `No.`, `No./ID`, `Last opened`, `Date created`, `Platform`, `Tags`, and any future optional columns.

Row actions still use the UI controls needed to operate AdsPower:

- row action buttons such as `Open` and `Close`
- row checkbox controls for toolbar actions
- row menu controls for rename and delete
- toolbar controls needed after a verified target row is selected

## Architecture

`core/adspower_ui.py` remains the shared Windows/macOS controller. The macOS AXUI backend and Windows UIA backend keep exposing pywinauto-shaped controls, while row interpretation is centralized in the controller.

The controller should resolve a row from the visible profile `ID` text. Optional chronology/order fields must never decide which row to open, close, rename, or delete. `Group`, `Name`, and `IP` may be parsed for discovery and diagnostics, but they are not a substitute for the exact target `ID`.

If the `ID` column is hidden, the controller must fail clearly and tell the operator to enable the AdsPower `ID` column. Acting from row order would be unsafe because the list can be filtered, sorted, or reordered.

## Testing

Add unit tests with fake accessibility controls that prove:

- old combined `No./ID` rows still scan correctly
- new separate `ID` and `#` rows scan correctly
- optional columns can be reordered or present without changing target resolution
- row actions align to the profile `ID` row, not the `#` row
- hidden/missing `ID` fails with an actionable error instead of guessing

Run focused AdsPower GUI tests before release.
