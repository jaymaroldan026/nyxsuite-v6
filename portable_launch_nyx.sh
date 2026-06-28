#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Remember the original args so we can re-exec verbatim after a macOS relocation.
NYX_ORIG_ARGS=("$@")

# The release ZIP (Compress-Archive) drops Unix exec bits. Restore them so the
# double-click launchers and the native-messaging host work on macOS/Linux.
chmod +x ./run_nyx_suite.command ./run_nyx_suite.sh ./portable_launch_nyx.sh \
  ./agent_host/host_main.sh ./agent_host/host_main.py 2>/dev/null || true

# --- macOS: relocate out of TCC-protected folders -------------------------
# On modern macOS a browser cannot launch the native-messaging host when the
# app lives in ~/Documents, ~/Desktop, ~/Downloads or iCloud Drive: the OS
# attributes the spawn to the browser, which has no access there, so the host
# dies and the extension's Connect fails with "Native host has exited".
# macos_relocate.py copies the app to ~/Library/Application Support/NyxSuite/app
# (never TCC-protected) and prints that path; we then re-exec from there. It is
# a fast no-op on Linux and when the app is already in a safe location.
if [[ "$(uname)" == "Darwin" && -f "$SCRIPT_DIR/scripts/macos_relocate.py" ]]; then
  NYX_RELO_PY="$(command -v python3 || true)"
  [[ -z "$NYX_RELO_PY" && -x /usr/bin/python3 ]] && NYX_RELO_PY="/usr/bin/python3"
  if [[ -n "$NYX_RELO_PY" ]]; then
    NYX_SAFE_DIR="$("$NYX_RELO_PY" "$SCRIPT_DIR/scripts/macos_relocate.py" || true)"
    if [[ -n "${NYX_SAFE_DIR:-}" && "$NYX_SAFE_DIR" != "$SCRIPT_DIR" && -x "$NYX_SAFE_DIR/portable_launch_nyx.sh" ]]; then
      cd "$NYX_SAFE_DIR"
      exec "$NYX_SAFE_DIR/portable_launch_nyx.sh" ${NYX_ORIG_ARGS[@]+"${NYX_ORIG_ARGS[@]}"}
    fi
  fi
fi

ENTRY_SCRIPT="bridge_app.py"
SETUP_ONLY=0
SKIP_BROWSER_INSTALL=0
SETUP_STAMP=".venv/.nyx_setup_stamp"
PLAYWRIGHT_STAMP=".venv/.nyx_playwright_stamp"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --entry-script)
      ENTRY_SCRIPT="${2:-bridge_app.py}"
      shift 2
      ;;
    --setup-only)
      SETUP_ONLY=1
      shift
      ;;
    --skip-browser-install)
      SKIP_BROWSER_INSTALL=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -x ".venv/bin/python3" ]]; then
  VENV_PYTHON=".venv/bin/python3"
elif [[ -x ".venv/bin/python" ]]; then
  VENV_PYTHON=".venv/bin/python"
else
  # macOS: prefer Homebrew python3 over system python (avoids SIP/Xcode issues)
  if [[ "$(uname)" == "Darwin" ]]; then
    for brew_python in "/opt/homebrew/bin/python3" "/usr/local/bin/python3"; do
      if [[ -x "$brew_python" ]]; then
        SYSTEM_PYTHON="$brew_python"
        break
      fi
    done
  fi
  if [[ -z "${SYSTEM_PYTHON:-}" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      SYSTEM_PYTHON="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      SYSTEM_PYTHON="$(command -v python)"
    else
      echo "Python 3 is required but was not found." >&2
      echo "Install via: brew install python3" >&2
      exit 1
    fi
  fi

  "$SYSTEM_PYTHON" -m venv .venv
  if [[ -x ".venv/bin/python3" ]]; then
    VENV_PYTHON=".venv/bin/python3"
  else
    VENV_PYTHON=".venv/bin/python"
  fi
fi

NEEDS_PYTHON_PACKAGES=0
if [[ ! -f "$SETUP_STAMP" || requirements.txt -nt "$SETUP_STAMP" ]]; then
  NEEDS_PYTHON_PACKAGES=1
elif ! "$VENV_PYTHON" -c "import greenlet, playwright.async_api, requests" >/dev/null 2>&1; then
  NEEDS_PYTHON_PACKAGES=1
fi

if [[ "$NEEDS_PYTHON_PACKAGES" -eq 1 ]]; then
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r requirements.txt
  touch "$SETUP_STAMP"
fi

if [[ "$SKIP_BROWSER_INSTALL" -ne 1 ]]; then
  if [[ ! -f "$PLAYWRIGHT_STAMP" || requirements.txt -nt "$PLAYWRIGHT_STAMP" ]]; then
    "$VENV_PYTHON" -m playwright install chromium
    touch "$PLAYWRIGHT_STAMP"
  fi
fi

if [[ "$SETUP_ONLY" -eq 1 ]]; then
  exit 0
fi

exec "$VENV_PYTHON" "$ENTRY_SCRIPT"
