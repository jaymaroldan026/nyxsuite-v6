# Extension Popup Queue Removal v6.4.0 Design

## Goal

Release NyxSuite v6.4.0 with lighter browser extension popups. The Nyx and Nyxify popups should no longer render their queue tables or selected-row queue actions, while the local backend queues and dashboard queue views remain unchanged.

## Approved Scope

Remove queue inspection from extension popups only.

- Nyx popup: remove the `Nyx Queue` collapsible section, search field, table, and row actions (`Mark Done`, `Relaunch`, `Close Profile`, `Remove Row`).
- Nyxify popup: remove the `Nyxify Queue` card, queue table, selected-row behavior, and selected-row actions (`Ban Proxy`, `Remove Row`).
- Keep dashboard queue views and local API queue endpoints unchanged.
- Keep runner controls, status counters, daily update, scrape tools, banned proxies, and broad runner actions that do not depend on selecting a popup queue row.
- Add `Setup & Install` to the Nyxify popup with the same behavior as Nyx: open the dashboard setup view when the bridge is running, or open the bundled setup helper page when it is not.
- Bump Nyx and Nyxify to v6.4.0, document the release, build the release ZIP, push `master`, and publish GitHub release `v6.4.0`.

## Approaches Considered

1. Remove only popup queue rendering and selected-row actions. This is the chosen approach because it cuts popup DOM work and live rerender churn without changing automation behavior.
2. Stop fetching queue rows from extension background status. This could reduce payload size but risks breaking counters, dashboard sync assumptions, or background merge logic without more investigation.
3. Remove queue actions from the dashboard too. This is out of scope because the user asked to remove queues only from the extensions.

## Architecture

The existing backend remains the source of truth. `core/nyx_controller.py`, `core/nyxify_controller.py`, local API queue endpoints, and `webui/dashboard.js` continue to expose full queue state and actions.

The popup layer becomes a control/status surface. Queue row arrays may still be present in status payloads, but popup scripts should no longer store them for table rendering or attach click handlers to queue row containers. This keeps the change low risk and avoids changing runner contracts during the release.

Nyxify setup uses the same bridge helper pattern already implemented in Nyx. Because extension resource URLs are scoped per extension, Nyxify needs its own bundled `setup.html` and `setup.js` files.

## Error Handling

Bridge startup and missing-native-host behavior should match the Nyx popup. If the native host is missing, Nyxify opens the bundled setup page instead of pointing the user back to the Nyx extension.

If the bridge is already running, Nyxify `Setup & Install` reuses the existing dashboard tab and deep-links to `#setup`.

## Testing

Add static regression tests that verify:

- Nyx popup no longer includes queue section IDs or selected-row queue controls.
- Nyx popup script no longer includes queue table rendering/event wiring.
- Nyxify popup no longer includes the queue card/table or selected-row queue controls.
- Nyxify popup script no longer includes selected-row queue rendering/event wiring.
- Nyxify popup includes `Setup & Install`, and bundled setup files exist.
- Both extension manifests and `VERSION` report v6.4.0 after version sync.

Run focused popup/version tests, release packaging tests, and build the release ZIP.
