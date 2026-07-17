╔══════════════════════════════════════════════════╗
║              NYX SUITE — Setup Guide             ║
║         One-time install · cross-platform        ║
╚══════════════════════════════════════════════════╝

Prerequisites
─────────────
• Python 3.9+ on PATH (the Python that ships with macOS works fine)
• AdsPower desktop app open and logged in (NyxSuite auto-connects — see below)
• A SnapBoard account with rows assigned to you
• (macOS) No Homebrew Python required

────────────────────────────────────────────────────
  AdsPower Local API (auto-connect — no key needed)
────────────────────────────────────────────────────

  Every task talks to AdsPower's Local API. NyxSuite connects to it
  AUTOMATICALLY — just keep the AdsPower desktop app open and logged in.
  No API key, no setup. This works the same on Windows and macOS.

  How it works: before each batch NyxSuite probes AdsPower's keyless
  /status endpoint (127.0.0.1:50325, falling back to local.adspower.net
  and whatever host AdsPower reports). When AdsPower is up, it just runs.

  If AdsPower is closed/not logged in, NyxSuite does NOT fail your tasks —
  it keeps your rows PENDING, shows a banner, and auto-resumes the moment
  AdsPower comes back (you never have to "Rerun Failed").

  Optional (most users never need this): if your AdsPower is configured
  to REQUIRE an API key, or runs on a non-default host/port, open the
  dashboard → Settings → Advanced Config (Nyx) and fill in
  "AdsPower API key" / Host / Port, then click "Test AdsPower connection".
  A saved key lives in data/nyx_config.json and is never shown back (leave
  the field blank to keep it). You can also set ADSPOWER_API_KEY /
  ADSP_API_KEY in the environment; the saved Settings key wins if both exist.

────────────────────────────────────────────────────
  macOS
────────────────────────────────────────────────────

  1. Open Terminal in this folder
  2. chmod +x *.sh *.command
  3. ./run_nyx_suite.command

  What happens:
    • If this folder is in Documents/Desktop/Downloads/iCloud, the app
      auto-installs to ~/Library/Application Support/NyxSuite/app and runs
      from there — macOS blocks browsers from launching it out of those
      protected folders (automatic, no action needed)
    • Creates .venv/ with Python virtual environment
    • Installs dependencies from requirements.txt
    • Downloads Playwright Chromium browser engine
    • Launches the bridge — dashboard opens in your browser

────────────────────────────────────────────────────
  Windows
────────────────────────────────────────────────────

  1. Open PowerShell as Admin in this folder
  2. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  3. .\portable_launch_nyx.ps1

  What happens:
    • Creates .venv/ with Python virtual environment
    • Installs dependencies from requirements.txt
    • Downloads Playwright Chromium browser engine
    • Launches the bridge — dashboard opens in your browser

────────────────────────────────────────────────────
  Linux
────────────────────────────────────────────────────

  1. Open a terminal in this folder
  2. chmod +x *.sh
  3. ./run_nyx_suite.sh

────────────────────────────────────────────────────
  After First Launch
────────────────────────────────────────────────────

  The bridge runs in your system tray (or headless).
  Open http://127.0.0.1:8870 in a browser.

  From the dashboard:
    • Settings → configure AdsPower host/port, groups, tags
    • Settings → install browser extensions (Chrome MV3)
    • Queue → manage tasks
    • Check for Updates → updates are applied in-app

  The bridge auto-registers the Chrome native messaging host on startup,
  so the browser extension can connect to the agent. No manual step needed.

  If you still see "Specified native messaging host not found" in the
  extension, close the bridge and run this once:
    python agent_host/install_host.py --register
  Then relaunch the bridge.

────────────────────────────────────────────────────
  Updating
────────────────────────────────────────────────────

  Future updates are handled in-app via the dashboard
  (Check for Update → Apply). No need to re-download.
