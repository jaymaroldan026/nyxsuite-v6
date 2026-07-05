import importlib
import sys
import unittest
from unittest import mock


class RunnerMacDockTests(unittest.TestCase):
    def _import_fresh(self, module_name):
        old_module = sys.modules.pop(module_name, None)
        try:
            return importlib.import_module(module_name)
        finally:
            sys.modules.pop(module_name, None)
            if old_module is not None:
                sys.modules[module_name] = old_module

    def test_nyx_runner_hides_python_dock_icon_on_import(self):
        with mock.patch("core.macos_dock.hide_macos_dock_icon") as hide:
            self._import_fresh("main")

        hide.assert_called_once_with()

    def test_nyxify_runner_hides_python_dock_icon_on_import(self):
        with mock.patch("core.macos_dock.hide_macos_dock_icon") as hide:
            self._import_fresh("nyxify_runner")

        hide.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
