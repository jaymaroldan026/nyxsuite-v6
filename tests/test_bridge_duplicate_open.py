import os
import unittest
from unittest import mock


class BridgeDuplicateOpenTests(unittest.TestCase):
    def test_duplicate_bridge_respects_no_open_environment(self):
        import bridge_app

        old_no_open = os.environ.get("NYXSUITE_NO_OPEN")
        os.environ["NYXSUITE_NO_OPEN"] = "1"
        try:
            with mock.patch("agent_host.install_host.register"), \
                 mock.patch.object(bridge_app.RunnerLock, "acquire", return_value=False), \
                 mock.patch.object(bridge_app.webbrowser, "open") as open_mock:
                bridge_app.main()
        finally:
            if old_no_open is None:
                os.environ.pop("NYXSUITE_NO_OPEN", None)
            else:
                os.environ["NYXSUITE_NO_OPEN"] = old_no_open

        open_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
