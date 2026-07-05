"""macOS Dock visibility helpers for source-run Python processes."""

import sys
from typing import Callable, List, Optional


def hide_macos_dock_icon(log: Optional[Callable[[str], None]] = None) -> List[str]:
    """Best-effort hide of Python.app from the Dock on macOS.

    Source runs use the Homebrew/Python.org ``Python.app`` launcher. Runner
    processes have no real UI, and the bridge only needs a menu-bar icon, so
    both should be accessory/UI-element apps instead of regular Dock apps.
    """
    if sys.platform != "darwin":
        return []

    errors: List[str] = []

    # Apply the older Process Manager transform first. This can take effect
    # before AppKit creates/activates NSApplication for the process.
    try:
        import ApplicationServices

        err, psn = ApplicationServices.GetCurrentProcess(None)
        if err == 0:
            ApplicationServices.TransformProcessType(
                psn,
                ApplicationServices.kProcessTransformToUIElementApplication,
            )
        else:
            errors.append(f"GetCurrentProcess returned {err}")
    except Exception as exc:
        errors.append(str(exc))

    try:
        import AppKit

        policy = getattr(AppKit, "NSApplicationActivationPolicyAccessory", 1)
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(policy)
    except Exception as exc:
        errors.append(str(exc))

    if errors and log:
        try:
            log(f"Could not fully hide macOS dock icon: {'; '.join(errors)}")
        except Exception:
            pass
    return errors
