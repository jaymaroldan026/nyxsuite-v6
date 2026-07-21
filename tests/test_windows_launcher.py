from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_nyx_suite_bat_runs_from_its_own_folder_and_pauses_on_failure():
    launcher = (ROOT / "run_nyx_suite.bat").read_text(encoding="ascii").lower()

    assert 'cd /d "%~dp0"' in launcher
    assert 'set "exit_code=%errorlevel%"' in launcher
    assert 'if not "%exit_code%"=="0" pause' in launcher
    assert "exit /b %exit_code%" in launcher


def test_windows_powershell_launcher_quotes_entry_script_for_spaced_paths():
    launcher = (ROOT / "portable_launch_nyx.ps1").read_text(encoding="ascii")

    assert "function Quote-ProcessArgument" in launcher
    assert "Quote-ProcessArgument -Value $Path" in launcher
    assert "Start-Process -FilePath $pythonExecutable -ArgumentList @($scriptArgument)" in launcher
