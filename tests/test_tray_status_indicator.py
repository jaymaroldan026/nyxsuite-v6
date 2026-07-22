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
    b._transparent_tray_icon = False
    b._tray_icon = None
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
        # The Nyx (blue) and Nyxify (gray) fills are actually present.
        self.assertIn((59, 130, 246, 255), nyx)
        self.assertIn((160, 162, 170, 255), nyxify)

    def test_transparent_tray_image_on_macos_keeps_click_target_size(self):
        b = _bridge(nyx_running=True, nyxify_running=True)
        b._transparent_tray_icon = True

        with mock.patch.object(bridge_app.sys, "platform", "darwin"):
            img = b._make_tray_image(True, True)

        self.assertEqual(img.size, (44, 44))
        self.assertEqual(img.mode, "RGBA")
        self.assertTrue(all(px == (0, 0, 0, 0) for px in img.getdata()))

    def test_transparent_setting_does_not_hide_non_macos_tray_image(self):
        b = _bridge(nyx_running=True, nyxify_running=False)
        b._transparent_tray_icon = True

        with mock.patch.object(bridge_app.sys, "platform", "win32"):
            img = b._make_tray_image(True, False)

        self.assertIn((59, 130, 246, 255), list(img.getdata()))

    def test_title_reflects_state(self):
        b = _bridge()
        self.assertIn("idle", b._tray_title(False, False))
        self.assertIn("Nyx running", b._tray_title(True, False))
        self.assertIn("Nyxify running", b._tray_title(False, True))
        both = b._tray_title(True, True)
        self.assertIn("Nyx running", both)
        self.assertIn("Nyxify running", both)


class TrayMenuSyncTests(unittest.TestCase):
    """The tray menu (Start/Stop enabled state + status lines) only tracks the
    live runner state if update_menu() is re-run when the state changes — pystray
    does NOT regenerate a native menu when it is opened. These cover that wiring.
    """

    def test_refresh_tray_menu_calls_update_menu(self):
        b = _bridge()
        icon = mock.Mock()
        b._tray_icon = icon
        # Force the non-darwin direct path so the call is synchronous.
        with mock.patch.object(bridge_app.sys, "platform", "win32"):
            b._refresh_tray_menu()
        icon.update_menu.assert_called_once()

    def test_refresh_tray_menu_noop_without_icon(self):
        b = _bridge()
        b._tray_icon = None
        b._refresh_tray_menu()  # must not raise

    def test_refresh_tray_menu_swallows_update_errors(self):
        b = _bridge()
        icon = mock.Mock()
        icon.update_menu.side_effect = RuntimeError("boom")
        b._tray_icon = icon
        with mock.patch.object(bridge_app.sys, "platform", "win32"):
            b._refresh_tray_menu()  # must not raise

    def test_status_updater_refreshes_menu_when_polling(self):
        """The background poll repaints the dot AND rebuilds the menu when the
        running state changes, so Start/Stop stops showing the wrong action."""
        import threading

        b = _bridge(nyx_running=True, nyxify_running=False)
        b._tray_icon = mock.Mock()
        b._stop = threading.Event()
        b._apply_tray_image = lambda image, title: None
        refreshed = threading.Event()
        b._refresh_tray_menu = lambda: refreshed.set()
        b._make_status_dot = lambda *s: None
        b._tray_title = lambda *s: "t"

        b._start_tray_status_updater()
        try:
            # First observed state differs from the initial None sentinel, so the
            # menu must be rebuilt on the first tick.
            self.assertTrue(refreshed.wait(5.0), "menu was never rebuilt while polling")
        finally:
            b._stop.set()


class TrayPreferenceActionTests(unittest.TestCase):
    def test_tray_icon_action_reports_current_preference(self):
        b = _bridge()
        b._transparent_tray_icon = True

        result = b._action_tray_icon({})

        self.assertTrue(result["ok"])
        self.assertTrue(result["transparent"])

    def test_set_tray_icon_saves_and_repaints_live_icon(self):
        b = _bridge(nyx_running=True, nyxify_running=False)
        b._transparent_tray_icon = False
        b._tray_icon = mock.Mock()
        b._apply_tray_image = mock.Mock()
        b._tray_title = mock.Mock(return_value="Nyx Suite - test")

        with mock.patch("bridge_app.save_bridge_config", return_value={"transparent_tray_icon": True}) as save:
            result = b._action_set_tray_icon({"transparent": True})

        save.assert_called_once_with({"transparent_tray_icon": True})
        self.assertTrue(result["ok"])
        self.assertTrue(result["transparent"])
        self.assertTrue(b._transparent_tray_icon)
        b._apply_tray_image.assert_called_once()


if __name__ == "__main__":
    unittest.main()
