"""Tests for OS color-scheme passthrough (core/browser_theme.py).

Part B removed the forced-dark override so automated pages follow the host OS
appearance and the site's own dark CSS renders (no more white editor).
"""

import asyncio
import types
import unittest
from unittest import mock

import core.browser_theme as bt


class ResolveOsColorSchemeTests(unittest.TestCase):
    def setUp(self):
        bt._CACHED_SCHEME = None

    def tearDown(self):
        bt._CACHED_SCHEME = None

    def test_macos_dark(self):
        with mock.patch.object(bt.sys, "platform", "darwin"), mock.patch.object(
            bt.subprocess, "run",
            return_value=types.SimpleNamespace(returncode=0, stdout="Dark\n"),
        ):
            self.assertEqual(bt.resolve_os_color_scheme(), "dark")

    def test_macos_light_when_key_absent(self):
        # `defaults read` exits non-zero (no key) in light mode.
        with mock.patch.object(bt.sys, "platform", "darwin"), mock.patch.object(
            bt.subprocess, "run",
            return_value=types.SimpleNamespace(returncode=1, stdout=""),
        ):
            self.assertEqual(bt.resolve_os_color_scheme(), "light")

    def test_result_is_cached(self):
        with mock.patch.object(bt.sys, "platform", "darwin"), mock.patch.object(
            bt.subprocess, "run",
            return_value=types.SimpleNamespace(returncode=0, stdout="Dark"),
        ) as run:
            self.assertEqual(bt.resolve_os_color_scheme(), "dark")
            self.assertEqual(bt.resolve_os_color_scheme(), "dark")
            self.assertEqual(run.call_count, 1)


class ApplyNativeColorSchemeTests(unittest.TestCase):
    def setUp(self):
        bt._CACHED_SCHEME = "dark"

    def tearDown(self):
        bt._CACHED_SCHEME = None

    def test_emulates_resolved_scheme(self):
        seen = {}

        class FakePage:
            async def emulate_media(self, color_scheme=None):
                seen["color_scheme"] = color_scheme

        asyncio.run(bt.apply_native_color_scheme_to_page(FakePage()))
        self.assertEqual(seen["color_scheme"], "dark")

    def test_no_forced_dark_injection(self):
        events = []

        class FakePage:
            async def emulate_media(self, color_scheme=None):
                events.append("emulate")

            async def add_init_script(self, *a, **k):
                events.append("init_script")

            async def evaluate(self, *a, **k):
                events.append("evaluate")

        asyncio.run(bt.apply_native_color_scheme_to_page(FakePage()))
        self.assertIn("emulate", events)
        # The dark-mode style/localStorage/matchMedia injection must be gone.
        self.assertNotIn("init_script", events)
        self.assertNotIn("evaluate", events)


if __name__ == "__main__":
    unittest.main()
