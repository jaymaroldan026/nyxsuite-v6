"""The macOS/Windows tray shows a color-dot status indicator, not the app icon.

Distinct colors per running product (Nyx vs Nyxify), a split dot when both run,
and a faint hollow ring when stopped. These tests cover the pure helpers that
decide the dot image and the tooltip/title text.
"""

import unittest
from unittest import mock

import bridge_app


def _bridge(nyx_running=False, nyxify_running=False):
    b = bridge_app.BridgeApp.__new__(bridge_app.BridgeApp)
    supervisor = mock.Mock()
    supervisor.is_running.side_effect = lambda name: (
        nyx_running if name == "nyx" else nyxify_running
    )
    b.supervisor = supervisor
    return b


class TrayStatusIndicatorTests(unittest.TestCase):
    def test_running_helpers_read_supervisor(self):
        b = _bridge(nyx_running=True, nyxify_running=False)
        self.assertTrue(b._nyx_running())
        self.assertFalse(b._nyxify_running())

    def test_running_helpers_swallow_supervisor_errors(self):
        b = bridge_app.BridgeApp.__new__(bridge_app.BridgeApp)
        b.supervisor = mock.Mock()
        b.supervisor.is_running.side_effect = RuntimeError("boom")
        self.assertFalse(b._nyx_running())
        self.assertFalse(b._nyxify_running())

    def test_dot_image_renders_for_every_state(self):
        b = _bridge()
        for state in [(False, False), (True, False), (False, True), (True, True)]:
            img = b._make_status_dot(*state)
            self.assertEqual(img.size, (44, 44))
            self.assertEqual(img.mode, "RGBA")

    def test_running_and_stopped_dots_differ(self):
        b = _bridge()
        stopped = list(b._make_status_dot(False, False).getdata())
        nyx = list(b._make_status_dot(True, False).getdata())
        nyxify = list(b._make_status_dot(False, True).getdata())
        both = list(b._make_status_dot(True, True).getdata())
        self.assertNotEqual(stopped, nyx)
        self.assertNotEqual(nyx, nyxify)
        self.assertNotEqual(nyx, both)
        self.assertNotEqual(nyxify, both)
        # The Nyx (violet) and Nyxify (cyan) fills are actually present.
        self.assertIn((139, 92, 246, 255), nyx)
        self.assertIn((6, 182, 212, 255), nyxify)

    def test_title_reflects_state(self):
        b = _bridge()
        self.assertIn("idle", b._tray_title(False, False))
        self.assertIn("Nyx running", b._tray_title(True, False))
        self.assertIn("Nyxify running", b._tray_title(False, True))
        both = b._tray_title(True, True)
        self.assertIn("Nyx running", both)
        self.assertIn("Nyxify running", both)


if __name__ == "__main__":
    unittest.main()
