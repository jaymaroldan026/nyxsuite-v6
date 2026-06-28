#!/bin/sh
# Native-messaging host launcher for macOS / Linux.
#
# Chrome execs the native host with a minimal environment (often a PATH that
# does NOT include Homebrew, sometimes barely usable). Relying on the
# `#!/usr/bin/env python3` shebath of host_main.py therefore fails with
# "Native host has exited" even when the script runs fine from a normal shell.
#
# This wrapper is launched via `#!/bin/sh` (always present, no PATH needed) and
# resolves an ABSOLUTE Python — preferring the project's venv (which also has
# the bridge's deps) — before exec'ing the real host. stdout MUST stay clean
# (native-messaging protocol only); diagnostics go to stderr.
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"

for PY in \
  "$ROOT/.venv/bin/python3" \
  "$ROOT/venv/bin/python3" \
  "$ROOT/.venv/bin/python" \
  "$ROOT/venv/bin/python" \
  /usr/bin/python3 \
  /usr/local/bin/python3 \
  /opt/homebrew/bin/python3 \
; do
  if [ -x "$PY" ]; then
    exec "$PY" "$DIR/host_main.py"
  fi
done

# Last resort: hope python3 is on PATH.
exec python3 "$DIR/host_main.py"
