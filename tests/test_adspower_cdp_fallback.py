"""Tests for the no-API CDP fallback (attach to a GUI-opened AdsPower profile
when the Local API is permission-gated).

Covers the DevToolsActivePort discovery/liveness logic in core.adspower_cdp and
the AdsPowerManager.open_profile / close_profile fallback wiring.
"""

import asyncio
import types
import unittest
from unittest import mock

import main
from core import adspower_cdp
from core import runner_flags
from core.adspower import (
    AdsPowerManager,
    AdsPowerPermissionError,
    AdsPowerProfileNotOpenError,
    AdsPowerUnreachableError,
    _coerce_bool,
)


def _write_dtap(base, dir_name, port, ws_path="/devtools/browser/abc-123"):
    profile_dir = base / dir_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    body = str(port) if ws_path is None else f"{port}\n{ws_path}"
    (profile_dir / "DevToolsActivePort").write_text(body, encoding="utf-8")
    return profile_dir


class CoerceBoolTests(unittest.TestCase):
    def test_real_bool_wins(self):
        self.assertTrue(_coerce_bool(True, "0", default=False))
        self.assertFalse(_coerce_bool(False, "1", default=True))

    def test_string_forms(self):
        self.assertTrue(_coerce_bool("yes", default=False))
        self.assertFalse(_coerce_bool("off", default=True))

    def test_none_and_unrecognized_skip_to_next_then_default(self):
        self.assertTrue(_coerce_bool(None, "", "true", default=False))
        self.assertEqual(_coerce_bool(None, "garbage", default="DEF"), "DEF")


class FindEndpointTests(unittest.TestCase):
    def setUp(self):
        self._base_patch = mock.patch.object(adspower_cdp, "_cache_base_dirs")
        self.mock_base_dirs = self._base_patch.start()
        self.addCleanup(self._base_patch.stop)

    def _point_cache_at(self, tmp_path):
        self.mock_base_dirs.return_value = [tmp_path]

    def test_direct_cache_dir_match_returns_live_ws(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write_dtap(base, "k1dyapw4_h12g1ac", 56612)
            self._point_cache_at(base)

            with mock.patch.object(adspower_cdp, "_port_is_listening", return_value=True), \
                 mock.patch.object(adspower_cdp, "_http_get_json",
                                   return_value={"webSocketDebuggerUrl": "ws://x"}):
                endpoint = adspower_cdp.find_open_profile_cdp_endpoint("k1dyapw4")

        self.assertEqual(endpoint, "ws://127.0.0.1:56612/devtools/browser/abc-123")

    def test_stale_devtools_file_ignored_when_port_dead(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write_dtap(base, "k1dyapw4_h12g1ac", 56612)
            self._point_cache_at(base)

            with mock.patch.object(adspower_cdp, "_port_is_listening", return_value=False):
                endpoint = adspower_cdp.find_open_profile_cdp_endpoint("k1dyapw4")

        self.assertEqual(endpoint, "")

    def test_unopened_profile_returns_empty(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write_dtap(base, "someoneelse_hash", 40000)
            self._point_cache_at(base)

            with mock.patch.object(adspower_cdp, "_port_is_listening", return_value=True), \
                 mock.patch.object(adspower_cdp, "_http_get_json", return_value={"id": "x"}):
                endpoint = adspower_cdp.find_open_profile_cdp_endpoint("k1dyapw4")

        self.assertEqual(endpoint, "")

    def test_secondary_match_by_start_page_serial(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Cache dir name does NOT contain the wanted serial, but the open
            # browser's start page advertises it.
            _write_dtap(base, "weirdname_hash", 45000)
            self._point_cache_at(base)

            def fake_http(session, port, path):
                if path == "/json/version":
                    return {"webSocketDebuggerUrl": "ws://x"}
                if path == "/json":
                    return [{"url": "https://start.adspower.net/?id=k1dyapw4&host=127.0.0.1:20725"}]
                return None

            with mock.patch.object(adspower_cdp, "_port_is_listening", return_value=True), \
                 mock.patch.object(adspower_cdp, "_http_get_json", side_effect=fake_http):
                endpoint = adspower_cdp.find_open_profile_cdp_endpoint("k1dyapw4")

        self.assertEqual(endpoint, "ws://127.0.0.1:45000/devtools/browser/abc-123")

    def test_list_open_profile_endpoints_prefers_start_page_serial(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write_dtap(base, "weirdname_hash", 45000)
            self._point_cache_at(base)

            def fake_http(session, port, path):
                if path == "/json/version":
                    return {"webSocketDebuggerUrl": "ws://x"}
                if path == "/json":
                    return [{"url": "https://start.adspower.net/?id=k1dyapw4&host=127.0.0.1:20725"}]
                return None

            with mock.patch.object(adspower_cdp, "_port_is_listening", return_value=True), \
                 mock.patch.object(adspower_cdp, "_http_get_json", side_effect=fake_http):
                endpoints = adspower_cdp.list_open_profile_endpoints()

        self.assertEqual(
            endpoints,
            {"k1dyapw4": "ws://127.0.0.1:45000/devtools/browser/abc-123"},
        )


class CacheBaseDirTests(unittest.TestCase):
    def test_macos_cwd_global_source_cache_root_is_discovered(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cache = home / "Library" / "Application Support" / "adspower_global" / "cwd_global" / "source" / "cache"
            cache.mkdir(parents=True)

            with mock.patch.object(adspower_cdp.Path, "home", return_value=home), \
                 mock.patch.object(adspower_cdp.os, "name", "posix"):
                dirs = adspower_cdp._cache_base_dirs()

        self.assertIn(cache, dirs)


class OpenProfileFallbackTests(unittest.TestCase):
    def _manager(self, fallback_enabled=True, ui_fallback=False):
        m = AdsPowerManager()
        m.control_mode = "auto"
        m.cdp_fallback_enabled = fallback_enabled
        # Default the GUI fallback OFF so these CDP-path tests never drive the
        # real AdsPower app; UI-path tests below enable it with a mock.
        m.ui_fallback_enabled = ui_fallback
        return m

    def test_attaches_when_profile_is_open(self):
        m = self._manager()
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint",
                        return_value="ws://127.0.0.1:56612/devtools/browser/abc"):
            endpoint = m.open_profile("k1dyapw4")
        self.assertEqual(endpoint, "ws://127.0.0.1:56612/devtools/browser/abc")
        self.assertIn("k1dyapw4", m._cdp_fallback_profiles)

    def test_permission_gated_but_profile_not_open_raises_not_open(self):
        m = self._manager()
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint", return_value=""):
            with self.assertRaises(AdsPowerProfileNotOpenError):
                m.open_profile("k1dyapw4")
        self.assertNotIn("k1dyapw4", m._cdp_fallback_profiles)

    def test_unreachable_with_nothing_open_reraises_unreachable(self):
        m = self._manager()
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerUnreachableError("app down"))
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint", return_value=""):
            with self.assertRaises(AdsPowerUnreachableError):
                m.open_profile("k1dyapw4")

    def test_unreachable_but_browser_open_attaches(self):
        m = self._manager()
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerUnreachableError("app down"))
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint",
                        return_value="ws://127.0.0.1:1/devtools/browser/x"):
            endpoint = m.open_profile("k1dyapw4")
        self.assertEqual(endpoint, "ws://127.0.0.1:1/devtools/browser/x")

    def test_disabled_fallback_reraises_original(self):
        m = self._manager(fallback_enabled=False)
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint",
                        return_value="ws://should-not-be-used") as finder:
            with self.assertRaises(AdsPowerPermissionError):
                m.open_profile("k1dyapw4")
            finder.assert_not_called()

    def test_ui_fallback_opens_when_permission_gated_and_not_open(self):
        """Permission-gated + profile not open + GUI fallback on -> drive the
        AdsPower GUI to open it, then return the CDP endpoint."""
        m = self._manager(ui_fallback=True)
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.open_profile_by_id.return_value = "ws://127.0.0.1:9/devtools/browser/z"
        m._ui_controller = mock.Mock(return_value=fake_ui)
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint", return_value=""):
            endpoint = m.open_profile("k1dyapw4")
        self.assertEqual(endpoint, "ws://127.0.0.1:9/devtools/browser/z")
        fake_ui.open_profile_by_id.assert_called_once_with("k1dyapw4")
        self.assertIn("k1dyapw4", m._cdp_fallback_profiles)

    def test_ui_fallback_failure_falls_through_to_not_open(self):
        m = self._manager(ui_fallback=True)
        m._open_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.open_profile_by_id.side_effect = RuntimeError("window not found")
        m._ui_controller = mock.Mock(return_value=fake_ui)
        with mock.patch("core.adspower_cdp.find_open_profile_cdp_endpoint", return_value=""):
            with self.assertRaises(AdsPowerProfileNotOpenError):
                m.open_profile("k1dyapw4")


class GroupResolutionNoApiTests(unittest.TestCase):
    """Regression: a permission-gated (9110) group/category fetch must propagate
    as AdsPowerPermissionError so create_profile falls back to the GUI — NOT get
    flattened to an empty list (which made resolve_group_id raise a misleading
    'group not found' and looped Nyxify forever)."""

    def _manager(self):
        m = AdsPowerManager.__new__(AdsPowerManager)
        return m

    def test_list_groups_propagates_permission_error(self):
        m = self._manager()
        m._get_json = mock.Mock(side_effect=AdsPowerPermissionError("9110 No local API permission"))
        with self.assertRaises(AdsPowerPermissionError):
            m.list_groups()

    def test_resolve_group_id_propagates_permission_not_group_not_found(self):
        m = self._manager()
        m._get_json = mock.Mock(side_effect=AdsPowerPermissionError("9110 No local API permission"))
        with self.assertRaises(AdsPowerPermissionError):
            m.resolve_group_id("Snapchat20")

    def test_list_extension_categories_propagates_permission_error(self):
        m = self._manager()
        m._get_json = mock.Mock(side_effect=AdsPowerPermissionError("9110 No local API permission"))
        with self.assertRaises(AdsPowerPermissionError):
            m.list_extension_categories()

    def test_create_profile_falls_back_to_gui_when_group_fetch_gated(self):
        m = AdsPowerManager()
        m.ui_fallback_enabled = True
        # The real gating point: every API call (incl. group fetch) is 9110.
        m._create_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.create_profile.return_value = {"profile_id": "k1new", "name": "Snapchat: Pending"}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        res = m.create_profile(name="Snapchat: Pending", proxy_value="1.2.3.4:9:u:p",
                               group_reference="Snapchat20")
        self.assertEqual(res.get("profile_id"), "k1new")
        fake_ui.create_profile.assert_called_once()

    def test_create_profile_fallback_forwards_gui_proxy_rotator(self):
        m = AdsPowerManager()
        m.ui_fallback_enabled = True
        m._create_profile_via_api = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.create_profile.return_value = {
            "profile_id": "k1new",
            "name": "Snapchat: Pending",
            "proxy": "2.2.2.2:2:u:p",
        }
        m._ui_controller = mock.Mock(return_value=fake_ui)
        proxy_rotator = mock.Mock(return_value="2.2.2.2:2:u:p")

        res = m.create_profile(
            name="Snapchat: Pending",
            proxy_value="1.1.1.1:1:u:p",
            group_reference="Snapchat20",
            proxy_rotator=proxy_rotator,
        )

        self.assertEqual(res.get("profile_id"), "k1new")
        fake_ui.create_profile.assert_called_once_with(
            name="Snapchat: Pending",
            proxy="1.1.1.1:1:u:p",
            group="Snapchat20",
            proxy_rotator=proxy_rotator,
        )


class ProxyCheckNoApiTests(unittest.TestCase):
    """In no-API mode the AdsPower proxy-check API is permission-gated; the
    pre-create rotation loop must NOT hard-fail — it falls through to the socket
    test so a reachable proxy still passes."""

    def _manager(self):
        m = AdsPowerManager.__new__(AdsPowerManager)
        m.parse_proxy = lambda v: {
            "proxy_type": "socks5", "proxy_host": "1.2.3.4",
            "proxy_port": "9999", "proxy_user": "u", "proxy_password": "p",
        }
        return m

    def test_permission_gated_checker_falls_back_to_socket(self):
        m = self._manager()
        m._post_json = mock.Mock(side_effect=AdsPowerPermissionError(
            "help (raw: {'code': 9110, 'msg': 'No local API permission'})"))
        m.test_proxy_connection = mock.Mock(return_value={"ok": True, "message": "socket ok"})
        res = m.check_proxy_via_adspower("1.2.3.4:9999:u:p", 20, True)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("fallback"), "socket")
        m.test_proxy_connection.assert_called_once()

    def test_permission_gated_unreachable_proxy_still_fails(self):
        m = self._manager()
        m._post_json = mock.Mock(side_effect=AdsPowerPermissionError(
            "help (raw: {'code': 9110, 'msg': 'No local API permission'})"))
        m.test_proxy_connection = mock.Mock(return_value={"ok": False, "message": "refused"})
        res = m.check_proxy_via_adspower("1.2.3.4:9999:u:p", 20, True)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("fallback"), "socket")


class CloseProfileFallbackTests(unittest.TestCase):
    def _gui(self, m):
        """Attach a mock UI controller so close/delete/rename never touch the GUI."""
        fake_ui = mock.Mock()
        m._ui_controller = mock.Mock(return_value=fake_ui)
        return fake_ui

    def test_close_cdp_closes_fallback_profile_before_gui(self):
        # A no-API (GUI-opened) profile is closed by draining that browser's
        # tabs over CDP first, avoiding another AdsPower GUI row search.
        m = AdsPowerManager()
        m.ui_fallback_enabled = True
        m._cdp_fallback_profiles.add("k1dyapw4")
        m._get_json = mock.Mock()
        fake_ui = self._gui(m)
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=True
        ) as close_tabs:
            result = m.close_profile("k1dyapw4")
        m._get_json.assert_not_called()              # never hits the gated stop API
        fake_ui.close_profile_by_id.assert_not_called()
        close_tabs.assert_called_once()
        self.assertEqual(close_tabs.call_args.args[0], "k1dyapw4")
        self.assertIs(close_tabs.call_args.kwargs["session"], m.session)
        self.assertFalse(close_tabs.call_args.kwargs["deep_scan"])
        self.assertEqual(result.get("msg"), "closed_via_cdp_tabs")
        # Stays marked no-API after closing so the immediately-following rename
        # goes straight to the GUI (Nyxify closes then renames). Cleared on delete.
        self.assertIn("k1dyapw4", m._cdp_fallback_profiles)

    def test_close_normal_profile_prefers_cdp_tabs_before_stop_api(self):
        m = AdsPowerManager()
        m._get_json = mock.Mock(return_value={"code": 0})
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=True
        ) as close_tabs:
            result = m.close_profile("normal-profile")

        close_tabs.assert_called_once()
        self.assertEqual(close_tabs.call_args.args[0], "normal-profile")
        self.assertIs(close_tabs.call_args.kwargs["session"], m.session)
        self.assertFalse(close_tabs.call_args.kwargs["deep_scan"])
        m._get_json.assert_not_called()
        self.assertEqual(result.get("msg"), "closed_via_cdp_tabs")

    def test_close_fallback_profile_uses_gui_when_cdp_tabs_not_available(self):
        m = AdsPowerManager()
        m.ui_fallback_enabled = True
        m._cdp_fallback_profiles.add("k1dyapw4")
        m._get_json = mock.Mock()
        fake_ui = self._gui(m)
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=False
        ):
            result = m.close_profile("k1dyapw4")

        m._get_json.assert_not_called()
        fake_ui.close_profile_by_id.assert_called_once_with("k1dyapw4")
        self.assertEqual(result.get("msg"), "closed_via_gui")

    def test_close_leaves_open_when_ui_fallback_disabled(self):
        m = AdsPowerManager()
        m.ui_fallback_enabled = False
        m._cdp_fallback_profiles.add("k1dyapw4")
        m._get_json = mock.Mock()
        result = m.close_profile("k1dyapw4")
        m._get_json.assert_not_called()
        self.assertEqual(result.get("msg"), "left_open_cdp_fallback")
        self.assertIn("k1dyapw4", m._cdp_fallback_profiles)   # stays marked no-API

    def test_close_normal_profile_calls_stop_api(self):
        m = AdsPowerManager()
        m.control_mode = "auto"
        m._get_json = mock.Mock(return_value={"code": 0})
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=False
        ):
            m.close_profile("normal-profile")
        m._get_json.assert_called_once()
        args, kwargs = m._get_json.call_args
        self.assertIn("/browser/stop", args[0])

    def test_close_permission_gated_api_profile_closes_via_gui(self):
        # A profile NOT in the fallback set whose stop API is permission-gated
        # still gets GUI-closed.
        m = AdsPowerManager()
        m.control_mode = "auto"
        m.ui_fallback_enabled = True
        m._get_json = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = self._gui(m)
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=False
        ):
            result = m.close_profile("normal-profile")
        fake_ui.close_profile_by_id.assert_called_once_with("normal-profile")
        self.assertEqual(result.get("msg"), "closed_via_gui")

    def test_close_unreachable_api_profile_closes_via_gui(self):
        m = AdsPowerManager()
        m.control_mode = "auto"
        m.ui_fallback_enabled = True
        m._get_json = mock.Mock(side_effect=AdsPowerUnreachableError("api down"))
        fake_ui = self._gui(m)
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=False
        ):
            result = m.close_profile("normal-profile")
        fake_ui.close_profile_by_id.assert_called_once_with("normal-profile")
        self.assertEqual(result.get("msg"), "closed_via_gui")

    def test_close_gui_failure_keeps_fallback_profile_marked_open(self):
        m = AdsPowerManager()
        m.ui_fallback_enabled = True
        m._cdp_fallback_profiles.add("k1dyapw4")
        fake_ui = self._gui(m)
        fake_ui.close_profile_by_id.side_effect = RuntimeError("button missing")
        with mock.patch.object(
            adspower_cdp, "close_open_profile_tabs", create=True, return_value=False
        ):
            result = m.close_profile("k1dyapw4")
        self.assertEqual(result.get("msg"), "gui_close_failed_left_open")
        self.assertIn("k1dyapw4", m._cdp_fallback_profiles)


class CloseOpenProfileTabsTests(unittest.TestCase):
    class _Page:
        def __init__(self, name):
            self.name = name
            self.closed = False
            self.close_kwargs = None

        def close(self, **kwargs):
            self.close_kwargs = kwargs
            self.closed = True

    class _Context:
        def __init__(self, pages):
            self._pages = pages

        @property
        def pages(self):
            return [page for page in self._pages if not page.closed]

    class _Browser:
        def __init__(self, contexts):
            self.contexts = contexts
            self.detached = False

        def close(self):
            self.detached = True

    class _PlaywrightContext:
        def __init__(self, browser):
            self.browser = browser
            self.connected_endpoint = None

        def __enter__(self):
            self.chromium = types.SimpleNamespace(connect_over_cdp=self._connect)
            return self

        def __exit__(self, *_exc):
            return False

        def _connect(self, endpoint):
            self.connected_endpoint = endpoint
            return self.browser

    def test_close_open_profile_tabs_closes_every_page_in_every_context(self):
        pages = [self._Page("one"), self._Page("two"), self._Page("three")]
        browser = self._Browser([
            self._Context(pages[:2]),
            self._Context(pages[2:]),
        ])
        factory_context = self._PlaywrightContext(browser)

        with mock.patch.object(
            adspower_cdp,
            "find_open_profile_cdp_endpoint",
            return_value="ws://127.0.0.1:4567/devtools/browser/abc",
        ):
            result = adspower_cdp.close_open_profile_tabs(
                "k1dyapw4",
                session=object(),
                playwright_factory=lambda: factory_context,
            )

        self.assertTrue(result)
        self.assertTrue(all(page.closed for page in pages))
        self.assertTrue(all(page.close_kwargs == {"run_before_unload": False} for page in pages))
        self.assertTrue(browser.detached)
        self.assertEqual(factory_context.connected_endpoint, "ws://127.0.0.1:4567/devtools/browser/abc")

    def test_close_open_profile_tabs_returns_false_without_live_endpoint(self):
        with mock.patch.object(adspower_cdp, "find_open_profile_cdp_endpoint", return_value=""):
            result = adspower_cdp.close_open_profile_tabs(
                "k1dyapw4",
                session=object(),
                playwright_factory=mock.Mock(),
            )

        self.assertFalse(result)


class UiModeSelectionTests(unittest.TestCase):
    """Nyx vs Nyxify run as separate processes and pick their own GUI mode:
    Nyxify -> assume_presearch=True (temp-name view), Nyx/default -> False
    (Profile-ID search). The override flows into the lazily-built controller."""

    def test_mode_flag_stored(self):
        self.assertIs(AdsPowerManager(ui_assume_presearch=True)._ui_assume_presearch, True)
        self.assertIs(AdsPowerManager(ui_assume_presearch=False)._ui_assume_presearch, False)
        self.assertIsNone(AdsPowerManager()._ui_assume_presearch)

    def test_override_applies_to_controller_config(self):
        import core.adspower_ui as aui
        if not aui._PYWINAUTO:
            self.skipTest("pywinauto not available")
        self.assertTrue(AdsPowerManager(ui_assume_presearch=True)._ui_controller().config.assume_presearch)
        self.assertFalse(AdsPowerManager(ui_assume_presearch=False)._ui_controller().config.assume_presearch)
        # Default (None) leaves the config's own default (env, default False = Nyx).
        self.assertFalse(AdsPowerManager()._ui_controller().config.assume_presearch)


class DeleteRenameGuiFallbackTests(unittest.TestCase):
    def _manager(self, ui_fallback=True):
        m = AdsPowerManager.__new__(AdsPowerManager)
        m._cdp_fallback_profiles = set()
        m.ui_fallback_enabled = ui_fallback
        return m

    def test_delete_fastpath_uses_gui_for_no_api_profile(self):
        m = self._manager()
        m._cdp_fallback_profiles.add("k1dyapw4")
        m._post_json = mock.Mock()                   # must NOT be called
        fake_ui = mock.Mock()
        fake_ui.delete_profile_by_id.return_value = {"code": 0, "deleted": True}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.delete_profile("k1dyapw4")
        m._post_json.assert_not_called()
        fake_ui.delete_profile_by_id.assert_called_once_with("k1dyapw4")
        self.assertEqual(data.get("code"), 0)
        self.assertNotIn("k1dyapw4", m._cdp_fallback_profiles)

    def test_delete_permission_gated_falls_back_to_gui(self):
        m = self._manager()
        m._post_json = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.delete_profile_by_id.return_value = {"code": 0, "deleted": True}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.delete_profile("k1dyapw4")
        fake_ui.delete_profile_by_id.assert_called_once_with("k1dyapw4")
        self.assertEqual(data.get("code"), 0)

    def test_delete_unreachable_falls_back_to_gui(self):
        m = self._manager()
        m._post_json = mock.Mock(side_effect=AdsPowerUnreachableError("api down"))
        fake_ui = mock.Mock()
        fake_ui.delete_profile_by_id.return_value = {"code": 0, "deleted": True}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.delete_profile("k1dyapw4")
        fake_ui.delete_profile_by_id.assert_called_once_with("k1dyapw4")
        self.assertEqual(data.get("code"), 0)

    def test_rename_fastpath_uses_gui_for_no_api_profile(self):
        m = self._manager()
        m._cdp_fallback_profiles.add("k1dyapw4")
        m._post_json = mock.Mock()                   # must NOT be called
        m.get_profile_name = mock.Mock()             # must NOT be called (also gated)
        fake_ui = mock.Mock()
        fake_ui.rename_profile_by_id.return_value = {"profile_id": "k1dyapw4", "name": "Snapchat: bob"}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.rename_profile("k1dyapw4", "Snapchat: bob")
        m._post_json.assert_not_called()
        m.get_profile_name.assert_not_called()
        fake_ui.rename_profile_by_id.assert_called_once_with("k1dyapw4", "Snapchat: bob")
        self.assertEqual(data.get("name"), "Snapchat: bob")

    def test_rename_permission_gated_falls_back_to_gui(self):
        m = self._manager()
        m.get_profile_name = mock.Mock(return_value="Snapchat: Pending")
        m._post_json = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        fake_ui = mock.Mock()
        fake_ui.rename_profile_by_id.return_value = {"profile_id": "k1dyapw4", "name": "Snapchat: bob"}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.rename_profile("k1dyapw4", "Snapchat: bob")
        fake_ui.rename_profile_by_id.assert_called_once_with("k1dyapw4", "Snapchat: bob")
        self.assertEqual(data.get("name"), "Snapchat: bob")

    def test_rename_unreachable_falls_back_to_gui(self):
        m = self._manager()
        m.get_profile_name = mock.Mock(side_effect=AdsPowerUnreachableError("api down"))
        m._post_json = mock.Mock(side_effect=AdsPowerUnreachableError("api down"))
        fake_ui = mock.Mock()
        fake_ui.rename_profile_by_id.return_value = {"profile_id": "k1dyapw4", "name": "Snapchat: bob"}
        m._ui_controller = mock.Mock(return_value=fake_ui)
        data = m.rename_profile("k1dyapw4", "Snapchat: bob")
        fake_ui.rename_profile_by_id.assert_called_once_with("k1dyapw4", "Snapchat: bob")
        self.assertEqual(data.get("name"), "Snapchat: bob")

    def test_disabled_ui_fallback_reraises_delete_failure(self):
        m = self._manager(ui_fallback=False)
        m._post_json = mock.Mock(side_effect=AdsPowerPermissionError("9110"))
        m._ui_controller = mock.Mock()
        with self.assertRaises(Exception):
            m.delete_profile("k1dyapw4")
        m._ui_controller.assert_not_called()


class _FakeStore:
    def __init__(self):
        self.calls = []

    def update_status(self, task_id, status, step, error=None, run_token=None):
        self.calls.append({"task_id": task_id, "status": status, "step": step, "error": error})
        return True


class ProcessTaskNotOpenTests(unittest.TestCase):
    """A not-open profile in no-API mode holds ONLY that row PENDING and must NOT
    trip the global health flag (other open profiles keep running)."""

    def setUp(self):
        runner_flags.nyx_clear_health()

    def tearDown(self):
        runner_flags.nyx_clear_health()

    def test_not_open_holds_pending_without_health_flag(self):
        store = _FakeStore()
        task = {"id": "t1", "profile_id": "k1dyapw4", "run_token": "tok"}

        async def boom(*_args, **_kwargs):
            raise AdsPowerProfileNotOpenError("not open")

        with mock.patch.object(main, "process_queued_task", side_effect=boom):
            asyncio.run(main.process_task(task, store, _FakeAds_for_main()))

        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["status"], "PENDING")
        self.assertEqual(store.calls[0]["step"], "waiting_for_profile_open")
        # The whole-queue health flag must stay clear.
        self.assertIsNone(runner_flags.nyx_get_health())

    def test_permission_error_still_sets_health_flag(self):
        store = _FakeStore()
        task = {"id": "t2", "profile_id": "k1dyapw4", "run_token": "tok"}

        async def boom(*_args, **_kwargs):
            raise AdsPowerPermissionError("9110")

        with mock.patch.object(main, "process_queued_task", side_effect=boom):
            asyncio.run(main.process_task(task, store, _FakeAds_for_main()))

        self.assertEqual(store.calls[0]["status"], "PENDING")
        self.assertEqual(store.calls[0]["step"], "blocked_adspower")
        health = runner_flags.nyx_get_health()
        self.assertIsNotNone(health)
        self.assertEqual(health.get("code"), "adspower_permission")


class _FakeAds_for_main:
    """Minimal stand-in; process_task only forwards it to process_queued_task,
    which is mocked, so no methods are actually exercised."""


if __name__ == "__main__":
    unittest.main()
