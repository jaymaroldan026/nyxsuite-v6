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


def _bridge(nyx_state="stopped", nyxify_state="stopped"):
    bridge = bridge_app.BridgeApp.__new__(bridge_app.BridgeApp)
    bridge.nyx = _FakeController(nyx_state)
    bridge.nyxify = _FakeController(nyxify_state)
    return bridge


class HotkeyActionTests(unittest.TestCase):
    def test_nyx_hotkey_stops_running_nyx(self):
        bridge = _bridge(nyx_state="running")

        result = bridge._toggle_product("nyx")

        self.assertEqual(result["action"], "stop")
        self.assertEqual(result["product"], "nyx")
        self.assertEqual(bridge.nyx.stopped, 1)
        self.assertEqual(bridge.nyx.started, 0)
        self.assertEqual(bridge.nyxify.stopped, 0)

    def test_nyxify_hotkey_stops_running_nyxify_even_while_nyx_stopped(self):
        # The old shared Ctrl+F8 controlled only the dashboard-selected product
        # (default nyx), so with Nyxify running it would START nyx instead of
        # stopping Nyxify. Dedicated keys must always act on their own product.
        bridge = _bridge(nyxify_state="running")

        result = bridge._toggle_product("nyxify")

        self.assertEqual(result["action"], "stop")
        self.assertEqual(result["product"], "nyxify")
        self.assertEqual(bridge.nyxify.stopped, 1)
        self.assertEqual(bridge.nyx.started, 0)
        self.assertEqual(bridge.nyx.stopped, 0)

    def test_hotkey_starts_stopped_product(self):
        bridge = _bridge()

        result = bridge._toggle_product("nyxify")

        self.assertEqual(result["action"], "start")
        self.assertEqual(bridge.nyxify.started, 1)
        self.assertEqual(bridge.nyxify.stopped, 0)

    def test_hotkey_stops_paused_and_blocked_states_too(self):
        for state in ("paused", "waiting", "blocked", "RUNNING"):
            bridge = _bridge(nyx_state=state)
            result = bridge._toggle_product("nyx")
            self.assertEqual(result["action"], "stop", state)
            self.assertEqual(bridge.nyx.stopped, 1, state)

    def test_hotkey_action_result_chooses_start_and_stop_tones(self):
        played = []

        def fake_play_async(fn):
            played.append(fn.__name__)

        with mock.patch.object(hotkeys, "_play_async", side_effect=fake_play_async):
            hotkeys.handle_start_stop_hotkey("bridge", lambda _scope: {"action": "start"})
            hotkeys.handle_start_stop_hotkey(
                "bridge", lambda _scope: {"action": "stop"}, label="Ctrl+F7")

        self.assertEqual(played, ["_play_start_tone", "_play_stop_tone"])


class HotkeyListenerBindingTests(unittest.TestCase):
    def test_start_product_hotkeys_registers_f7_and_f8(self):
        captured = {}

        class _FakeListener:
            def __init__(self, on_press=None, on_release=None):
                captured["on_press"] = on_press
                captured["on_release"] = on_release
                self.daemon = False

            def start(self):
                captured["started"] = True

            def stop(self):
                pass

        class _FakeKey:
            def __init__(self, name):
                self.name = name

        class _Key:
            ctrl = _FakeKey("ctrl")
            ctrl_l = _FakeKey("ctrl_l")
            ctrl_r = _FakeKey("ctrl_r")
            f7 = _FakeKey("f7")
            f8 = _FakeKey("f8")

        fake_keyboard = SimpleNamespace(Key=_Key, Listener=_FakeListener)
        fired = []

        hotkeys.stop_hotkey()
        try:
            with mock.patch.dict(
                "sys.modules", {"pynput": SimpleNamespace(keyboard=fake_keyboard),
                                "pynput.keyboard": fake_keyboard}):
                listener = hotkeys.start_product_hotkeys({
                    "f8": ("nyx", lambda scope: fired.append(("nyx", scope)) or {"action": "stop"}),
                    "f7": ("nyxify", lambda scope: fired.append(("nyxify", scope)) or {"action": "stop"}),
                })
                self.assertIsNotNone(listener)
                self.assertTrue(captured.get("started"))

                with mock.patch.object(hotkeys, "_play_async", lambda fn: None):
                    # F8 without Ctrl: no fire.
                    captured["on_press"](_Key.f8)
                    self.assertEqual(fired, [])
                    # Ctrl+F8 -> nyx, Ctrl+F7 -> nyxify.
                    captured["on_press"](_Key.ctrl)
                    captured["on_press"](_Key.f8)
                    captured["on_press"](_Key.f7)
                    captured["on_release"](_Key.ctrl)
                    # F7 after Ctrl released: no fire.
                    captured["on_press"](_Key.f7)

                self.assertEqual(fired, [("nyx", "nyx"), ("nyxify", "nyxify")])
        finally:
            hotkeys.stop_hotkey()


if __name__ == "__main__":
    unittest.main()
