import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import startup


class MacStartupTrayTests(unittest.TestCase):
    def test_macos_launch_agent_keeps_tray_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with mock.patch.object(startup.Path, "home", return_value=home), \
                 mock.patch.object(startup, "_resolve_launch_command", return_value="/tmp/run-bridge"), \
                 mock.patch.object(startup.os, "system") as system:
                startup._set_macos(True)

            plist = home / "Library" / "LaunchAgents" / "com.nyxsuite.agent.plist"
            text = plist.read_text(encoding="utf-8")

        self.assertNotIn("NYXSUITE_NO_TRAY", text)
        self.assertIn("NYXSUITE_NO_OPEN", text)
        system.assert_called_once()


if __name__ == "__main__":
    unittest.main()
