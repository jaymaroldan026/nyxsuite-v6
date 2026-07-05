import unittest
from types import SimpleNamespace
from unittest import mock

import bridge_app
from core import hotkeys


class _FakeController:
    def __init__(self, state):
        self.state = state
        self.started = 0
        self.stopped = 0

    def status_snapshot(self):
        return {"bot": {"state": self.state}}

    def start(self, _payload=None):
        self.started += 1
        self.state = "running"
        return {"ok": True, "message": "started"}

    def stop(self, _payload=None):
        self.stopped += 1
        self.state = "stopped"
        return {"ok": True, "message": "stopped"}


class HotkeyActionTests(unittest.TestCase):
    def test_bridge_hotkey_uses_dashboard_stop_for_active_product(self):
        bridge = bridge_app.BridgeApp.__new__(bridge_app.BridgeApp)
        bridge.nyx = _FakeController("running")
        bridge.nyxify = _FakeController("stopped")
        bridge._hotkey_product = "nyx"

        result = bridge._toggle_hotkey_product()

        self.assertEqual(result["action"], "stop")
        self.assertEqual(bridge.nyx.stopped, 1)
        self.assertEqual(bridge.nyx.started, 0)
        self.assertEqual(bridge.nyxify.stopped, 0)

    def test_bridge_hotkey_uses_dashboard_start_for_active_product(self):
        bridge = bridge_app.BridgeApp.__new__(bridge_app.BridgeApp)
        bridge.nyx = _FakeController("stopped")
        bridge.nyxify = _FakeController("stopped")
        bridge._hotkey_product = "nyxify"

        result = bridge._toggle_hotkey_product()

        self.assertEqual(result["action"], "start")
        self.assertEqual(bridge.nyxify.started, 1)
        self.assertEqual(bridge.nyxify.stopped, 0)

    def test_hotkey_action_result_chooses_start_and_stop_tones(self):
        played = []

        def fake_play_async(fn):
            played.append(fn.__name__)

        with mock.patch.object(hotkeys, "_play_async", side_effect=fake_play_async):
            hotkeys.handle_start_stop_hotkey("bridge", lambda _scope: {"action": "start"})
            hotkeys.handle_start_stop_hotkey("bridge", lambda _scope: {"action": "stop"})

        self.assertEqual(played, ["_play_start_tone", "_play_stop_tone"])


if __name__ == "__main__":
    unittest.main()
