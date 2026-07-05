import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class AgentHostMacOSLaunchdTests(unittest.TestCase):
    def test_start_agent_uses_launchd_on_macos(self):
        from agent_host import host_main

        launch_result = {"ok": True, "message": "Agent started via launchd."}

        with mock.patch.object(host_main.sys, "platform", "darwin"), \
             mock.patch.object(host_main, "_start_agent_via_launchd", return_value=launch_result) as launchd_start, \
             mock.patch.object(host_main.subprocess, "Popen") as popen:
            result = host_main._start_agent()

        self.assertEqual(result, launch_result)
        launchd_start.assert_called_once()
        popen.assert_not_called()

    def test_launchd_plist_preserves_command_and_environment(self):
        from agent_host import host_main

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "com.nyxsuite.bridge.plist"
            env = {
                "NYXSUITE_NO_OPEN": "1",
                "NYXSUITE_NO_TRAY": "",
                "IGNORED_NONE": None,
            }

            host_main._write_macos_launchd_agent(
                path=path,
                cmd=["/venv/bin/python", "/app/bridge_app.py"],
                cwd=Path("/app"),
                env=env,
            )

            data = plistlib.loads(path.read_bytes())

        self.assertEqual(data["Label"], "com.nyxsuite.bridge")
        self.assertEqual(data["ProgramArguments"], ["/venv/bin/python", "/app/bridge_app.py"])
        self.assertEqual(data["WorkingDirectory"], "/app")
        self.assertEqual(data["EnvironmentVariables"]["NYXSUITE_NO_OPEN"], "1")
        self.assertNotIn("NYXSUITE_NO_TRAY", data["EnvironmentVariables"])
        self.assertNotIn("IGNORED_NONE", data["EnvironmentVariables"])


if __name__ == "__main__":
    unittest.main()
