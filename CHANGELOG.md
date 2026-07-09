# Changelog

## 6.0.7 — Bitmoji outfit fallback, roll back to any version, Windows Chrome-kill fix, SnapBoard auto-refresh

### Bitmoji: stop "scrolling forever" when an item leaves the catalog
- Bitmoji rotates its clothing catalog, so configured outfit item ids (e.g.
  `bottom=788`, and every currently-configured footwear id) periodically stop
  existing. The exact-match scan then never found them, scrolled the panel to the
  bottom, and failed the whole profile — the "scroll forever" symptom. Outfit
  selection now still **prefers** the configured item, but when its id is gone it
  falls back to any available item of the same category so the avatar still gets
  dressed (deterministic per profile, skips blocked ids). Toggle with
  `NYX_OUTFIT_FALLBACK_ANY=0` for strict exact-item behaviour.
- Also bounded the Bitmoji panel scroll calls (were able to hang ~30s each) so a
  slow-rendering category can't stall the run.

### Updates: roll back to any published version
- The rollback picker now lists **every** published release, not just local
  snapshots — pick any older version in Dashboard → Settings and it downloads and
  applies that release if no local backup exists. Local backups kept bumped from
  2 to 20 (env `NYX_KEEP_BACKUPS`).

### Windows: running the GUI no longer kills Chrome
- Fixed a PID-reuse bug where a recycled process id that now belonged to
  `chrome.exe` could be trusted or force-killed as if it were our runner. The
  runner now verifies a pid actually belongs to our process (image/cmdline)
  before trusting or terminating it.

### Nyxify: SnapBoard auto-refresh + email/phone OTP retry parity
- When an email or phone OTP fetch comes back "no pending order for this account"
  (often just a stale SnapBoard tab), Nyxify now refreshes the SnapBoard tab
  (with a cooldown) and retries. Phone OTP got the same no-pending retry and
  back-button recovery that email already had.

### Snapchat signup: login-phase stall fix
- Bounded the `scroll_into_view` on the Snapchat username/login field (was able
  to block ~30s and stall the signup) to a short, non-fatal timeout.

### Nyx extension: daily-update AdsPower id now auto-saves
- The Start-ID field in the extension popup now debounced-auto-saves as you type
  (and on blur). Previously the 15s panel refresh wiped the typed id because it
  was never persisted.

## 6.0.6 — macOS tray color fix, tiny dot, restart controls

- Fixes the macOS menu-bar dot rendering monochrome/black: the icon is now
  installed as a non-template NSImage and repainted on the main thread (AppKit
  UI mutations from the background poll thread were silently ignored, so the
  color never showed). The dot is now a small color indicator.
- Recolors the indicator: **blue** while Nyx is running, **gray** while Nyxify
  is running, a split blue/gray dot when both run, a faint ring when idle.
- Makes the dot **tiny** (small padded glyph) instead of filling the menu bar.
- Adds **Restart Nyx** and **Restart Nyxify** to the tray menu alongside
  Start/Stop.

## 6.0.5 — Auto-retry transient Bitmoji fails, macOS tray redesign, parallel-create dedup

### Bitmoji: auto-retry the whole profile before failing
- A generic Bitmoji step failure (a category/trait panel that didn't render in
  time) now re-runs the whole profile automatically before the row is marked
  FAILED — the same thing users did by hand with "reset failed → rerun", which
  is why those reruns succeeded. Terminal results (banned / dead proxy / browser
  closed / already-has-bitmoji) are never retried. Tunable via
  `NYX_BITMOJI_PROFILE_RETRIES` (default 2 extra attempts) and
  `NYX_BITMOJI_RETRY_BACKOFF_SECONDS`. Cross-platform (Windows + macOS).

### Nyxify: two parallel creates can no longer merge onto one profile
- Fixed the race where two parallel profile creations resolved to the **same**
  AdsPower id — so two signups ran on one profile and the same id was written
  into two SnapBoard rows. Profile-id discovery now keys off the set of ids
  present *before* the create and a process-wide assigned-id registry, so it
  always returns the genuinely-new id and never one already handed to another
  create. Robust against transient accessibility mis-reads of the serial
  watermark that used to make it return the newest (other task's) row.

### macOS/Windows tray redesign
- The menu-bar item is now a **color status dot**, not the app icon: violet when
  Nyx is running, cyan when Nyxify is running, a split dot when both run, and a
  faint hollow ring (near-invisible but still clickable) when idle. It repaints
  live as runners start and stop.
- The dropdown is flat: **Start/Stop for both Nyx and Nyxify are shown directly**
  (no submenu to hover into), each with a live "running / stopped" status line,
  and Start/Stop enable based on the current state. The Dock icon stays hidden.

## 6.0.4 — Bitmoji completion, warm-up unblock, deleted-profile handling, SnapBoard sign-in

### Bitmoji: complete every profile (no random stops)
- Trait, paired-earring and outfit steps now retry as a whole unit: a step that
  can't land re-opens its category/subcategory panel, waits for the items to
  actually render, then clicks the *same* intended item again. The random
  "stops at paired earrings / outfit" failures were a click firing into a panel
  that had switched category but not yet painted — never a wrong selector, so
  the fix only makes the correct choice land, it never bypasses or substitutes.
- Tunable via `BITMOJI_STEP_CLICK_RETRIES`, `BITMOJI_STEP_UNIT_RETRIES`,
  `BITMOJI_PANEL_ITEMS_TIMEOUT`.

### Cookie warm-up no longer blocks signup (Windows hang)
- Warm-up pages now auto-dismiss any `beforeunload`/alert/confirm dialog a stray
  navigation click raises — an unanswered dialog used to freeze the tab and its
  close, so the site never closed and signup never started (manually closing the
  tab was the known workaround). Page close is also timeout-guarded and skips
  the beforeunload handler.
- Hard per-site and whole-phase caps (`NYXIFY_COOKIE_WARMUP_PER_SITE_HARD_TIMEOUT`,
  `NYXIFY_COOKIE_WARMUP_TOTAL_HARD_TIMEOUT`) guarantee warm-up always yields to
  the signup even if a site wedges.

### Deleted Nyxify profiles no longer run under Nyx
- When Nyxify deletes a profile (failed-signup cleanup, stale-pending cleanup,
  or a Replace action) its Nyx queue row is removed and the id archived, so Nyx
  never opens a deleted profile just to fail with `profile_missing`, and an
  extension/SnapBoard re-sync can't re-queue it.
- A run-time `profile_missing` also archives the id for the same reason.

### Nyx auto sign-in uses the SnapBoard password
- When a profile's Snapchat session has dropped and the **sign-in** page shows
  (the account exists but is logged out), Nyx now signs back in with the
  SnapBoard row's Password and the username Nyxify confirmed — not a fixed
  default. The sign-in walk is more resilient (waits for the form, retries both
  steps, ignores the un-renamed temp profile name as a username) and can recover
  a session that drops mid-flow instead of timing out.

### Nyxify: extension turn-off during account creation is now opt-in
- The Chrome-extension disabling step during signup is OFF by default (new
  "Disable extensions on create" toggle in Nyxify settings). The browser open,
  cookie warm-up and signup are unchanged; extensions are simply left as
  configured while the account is created.

### Editable accounts-per-hour (Nyx extension)
- The Daily Report's expected-hours rate is now an editable "Accounts / hour"
  field (persisted) instead of a fixed 7.

## 6.0.3 — Per-product hotkeys, full stop, and Bitmoji queue unblocking

### Hotkeys: Ctrl+F8 = Nyx, Ctrl+F7 = Nyxify
- Each product now has its own dedicated global stop/start hotkey: **Ctrl+F8**
  always controls Nyx and **Ctrl+F7** always controls Nyxify. The old shared
  Ctrl+F8 acted on whichever dashboard tab was viewed last (default Nyx), so
  with Nyxify running it could fail to stop it — or start Nyx instead.
- A hotkey stop is the same **full stop** as the dashboard Stop button, and the
  supervisor now confirms the runner actually died: a runner that survives the
  normal kill (e.g. wedged in a blocking call) is force-killed within ~3s.

### Nyx profiles stuck "waiting for Nyxify" (Bitmoji not proceeding)
- With continuous mode on, any queued Nyxify work used to hold **every** Nyx
  profile that had no matching Nyxify row — old, fully signed-up profiles never
  started their Bitmoji run. The guard now only holds while a signup is
  actively RUNNING, and only for a bounded id-sync window (15 min, tunable via
  `NYXIFY_PROFILE_SYNC_HOLD_MAX_SECONDS`).
- A Nyxify row that failed **after** the Snapchat account was real (rename /
  close / handoff bookkeeping hiccups) no longer parks its Nyx row forever —
  the Bitmoji run proceeds and the bookkeeping problem stays visible on the
  Nyxify row.
- A Nyxify row that failed **before** an account existed now fails the Nyx row
  visibly as `nyxify_signup_failed` instead of re-holding it every poll.
- Every "waiting for Nyxify" hold is now bounded: a crashed/stale Nyxify can
  no longer park Nyx rows indefinitely (10-min staleness valve, tunable via
  `NYXIFY_BOOKKEEPING_STALE_SECONDS`).

### Continuous mode
- Bitmoji creation now reliably continues once the account is real: an
  AdsPower rename failure no longer blocks the SnapBoard id push or the Nyx
  handoff (the rename problem is still recorded on the row).
- Nyx can no longer interrupt account creation: the completed-signup row is
  published as `closing_profile` while Nyxify is still closing/renaming the
  profile, and only becomes ready (`profile_closed` / `profile_close_failed`)
  when Nyxify is done with it. Previously Nyx could open the profile mid-close
  and the fresh Bitmoji run died with `manual_terminate`.
- The last handoff of a batch no longer strands below the start threshold:
  a held handoff re-arms the flush latch so it is retried on the next poll.

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
