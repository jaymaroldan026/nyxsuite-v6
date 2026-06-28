import os
import shutil
import subprocess
from pathlib import Path


HUBSTAFF_ENV_KEY = "HUBSTAFF_CLI"


def _candidate_paths(configured_path=""):
    configured = str(configured_path or "").strip().strip('"')
    if configured:
        yield configured

    env_path = str(os.getenv(HUBSTAFF_ENV_KEY) or "").strip().strip('"')
    if env_path:
        yield env_path

    if os.name == "nt":
        install_roots = [
            os.getenv("ProgramFiles"),
            os.getenv("ProgramFiles(x86)"),
            os.getenv("LOCALAPPDATA"),
        ]
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            install_roots.append(str(Path(local_app_data) / "Programs"))
        for root in install_roots:
            if not root:
                continue
            root_path = Path(root)
            yield str(root_path / "Hubstaff" / "HubstaffCLI.exe")
            yield str(root_path / "Hubstaff" / "HubstaffCLI" / "HubstaffCLI.exe")
            yield str(root_path / "Hubstaff" / "HubstaffCLI" / "HubstaffCLI")
    else:
        yield str(Path.home() / "Applications" / "Hubstaff.app" / "Contents" / "MacOS" / "HubstaffCLI")
        yield str(Path("/Applications/Hubstaff.app/Contents/MacOS/HubstaffCLI"))
        yield str(Path("/usr/local/bin/HubstaffCLI"))
        yield str(Path("/opt/homebrew/bin/HubstaffCLI"))


def resolve_hubstaff_cli(configured_path=""):
    for candidate in _candidate_paths(configured_path):
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())

    for command in ("HubstaffCLI.exe", "HubstaffCLI"):
        resolved = shutil.which(command)
        if resolved:
            return resolved

    raise FileNotFoundError(
        "Could not find HubstaffCLI. Install Hubstaff, set HUBSTAFF_CLI, or enter the full HubstaffCLI path."
    )


def run_hubstaff_cli(command, cli_path="", timeout=20):
    resolved_cli = resolve_hubstaff_cli(cli_path)
    args = [resolved_cli, str(command or "").strip()]
    if not args[1]:
        raise ValueError("Hubstaff command is required.")

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=max(1, int(timeout or 20)),
        creationflags=creationflags,
        check=False,
    )
    output = ((completed.stdout or "") + ("\n" if completed.stdout and completed.stderr else "") + (completed.stderr or "")).strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"HubstaffCLI {args[1]} failed with exit code {completed.returncode}."
            + (f" Output: {output}" if output else "")
        )

    return {
        "cli_path": resolved_cli,
        "output": output,
    }


def stop_hubstaff(cli_path=""):
    status_result = run_hubstaff_cli("status", cli_path=cli_path, timeout=20)
    stop_result = run_hubstaff_cli("stop", cli_path=status_result["cli_path"], timeout=20)
    return {
        "ok": True,
        "cli_path": status_result["cli_path"],
        "status_output": status_result.get("output", ""),
        "stop_output": stop_result.get("output", ""),
    }
