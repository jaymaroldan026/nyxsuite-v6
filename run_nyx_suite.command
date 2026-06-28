#!/usr/bin/env bash
# Launch the Nyx Suite bridge (web dashboard + menu-bar tray) on macOS (double-clickable).
#
# First run installs the venv, dependencies, and the Playwright browser in the
# foreground so you can watch progress. The bridge then starts DETACHED, so you
# can close this Terminal window and it keeps running (menu-bar icon only — no
# Dock icon). On later runs the setup step is a fast no-op.
#
# After first setup you normally never need this window again: use the "Connect"
# button in the Nyx browser extension to start/stop the bridge.
cd "$(dirname "$0")"

# Step 1 — first-run setup (venv + deps + Playwright). Fast no-op on later runs.
if bash ./portable_launch_nyx.sh --entry-script bridge_app.py --setup-only; then
  # Step 2 — start the bridge detached so closing this window won't stop it.
  nohup bash ./portable_launch_nyx.sh --entry-script bridge_app.py --skip-browser-install >/dev/null 2>&1 &
  disown 2>/dev/null || true
  echo ""
  echo "Nyx Suite is running in the background (look for the menu-bar icon)."
  echo "You can close this window — the bridge will keep running."
else
  echo ""
  echo "Setup failed — see the messages above."
  exit 1
fi
