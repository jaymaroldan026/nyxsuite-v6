import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shell_release_zip_uses_portable_native_host_manifest(tmp_path):
    output_dir = tmp_path / "release"
    secret_file = ROOT / "core" / "license_runtime_secret.py"
    secret_file.write_text('SECRET = "do-not-ship"\n', encoding="utf-8")
    try:
        subprocess.run(
            [
                "bash",
                str(ROOT / "packaging" / "create_release_zip.sh"),
                "--version",
                "9.9.9-test",
                "--output-dir",
                str(output_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        secret_file.unlink(missing_ok=True)

    zip_path = output_dir / "NyxSuite-v9.9.9-test.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(
            archive.read("NyxSuite-v9.9.9-test/agent_host/com.nyxsuite.agent.json")
        )
        update_config = json.loads(
            archive.read("NyxSuite-v9.9.9-test/update_config.json")
        )

    assert manifest["path"] == "agent_host/host_main.py"
    assert "NyxSuite-v9.9.9-test/core/license_runtime_secret.py" not in names
    assert "NyxSuite-v9.9.9-test/ui_templates/adspower/elements/new_profile_btn.png" in names
    assert update_config["repo"] == "jaymaroldan026/nyxsuite-v6"
    assert update_config["asset_pattern"] == "NyxSuite-v*.zip"


def test_shell_release_zip_accepts_relative_output_dir(tmp_path):
    relative_output = "relative-release"
    subprocess.run(
        [
            "bash",
            str(ROOT / "packaging" / "create_release_zip.sh"),
            "--version",
            "9.9.8-test",
            "--output-dir",
            relative_output,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    assert (tmp_path / relative_output / "NyxSuite-v9.9.8-test.zip").exists()
