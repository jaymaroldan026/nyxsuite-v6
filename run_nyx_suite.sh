#!/usr/bin/env bash
# Launch the Nyx Suite bridge (web dashboard + tray) on macOS / Linux.
#
# First run installs the venv, dependencies, and the Playwright browser in the
# foreground. The bridge then starts DETACHED, so you can close this terminal
# and it keeps running. On later runs the setup step is a fast no-op.
#
# After first setup you normally never need this terminal again: use the
# "Connect" button in the Nyx browser extension to start/stop the bridge.
cd "$(dirname "$0")"

# Step 1 — first-run setup (venv + deps + Playwright). Fast no-op on later runs.
if bash ./portable_launch_nyx.sh --entry-script bridge_app.py --setup-only; then
  # Step 2 — start the bridge detached so closing this terminal won't stop it.
  nohup bash ./portable_launch_nyx.sh --entry-script bridge_app.py --skip-browser-install >/dev/null 2>&1 &
  disown 2>/dev/null || true
  echo ""
  echo "Nyx Suite is running in the background. You can close this terminal."
else
  echo ""
  echo "Setup failed — see the messages above."
  exit 1
fi
