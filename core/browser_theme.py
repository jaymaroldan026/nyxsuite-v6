"""Color-scheme handling for automated pages.

This module used to *force* dark mode (injected CSS, patched ``matchMedia``, a
``MutationObserver`` re-applying dark markers, etc.). That fought each site's own
theming: the Bitmoji editor is dark only via ``@media(prefers-color-scheme:
dark)`` and rendered **white** whenever Playwright left the page in light, then
snapped back to dark once the run finished.

We now simply mirror the host OS appearance on every automated page, so the
site's own light/dark CSS activates exactly as it does when a human uses the
browser — no injected colors, no overrides. Playwright clears the emulation when
it disconnects, so the browser returns to its normal (OS) appearance on its own.

The old public names are kept as thin aliases so existing call sites keep working
with the new, correct behavior.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys

# Resolved once per process: reading the OS appearance is cheap but not free, and
# it does not change mid-run in any way we care about.
_CACHED_SCHEME = None


def resolve_os_color_scheme():
    """Return ``"dark"`` or ``"light"`` for the host OS appearance (cached).

    macOS: ``defaults read -g AppleInterfaceStyle`` prints ``Dark`` in dark mode
    and errors (no key) in light mode. Windows: the ``AppsUseLightTheme`` registry
    value is ``0`` in dark mode. Anything unknown falls back to ``"light"``.
    """
    global _CACHED_SCHEME
    if _CACHED_SCHEME is not None:
        return _CACHED_SCHEME

    scheme = "light"
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and "dark" in (result.stdout or "").strip().lower():
                scheme = "dark"
        elif sys.platform.startswith("win"):
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            try:
                apps_use_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                scheme = "light" if apps_use_light else "dark"
            finally:
                winreg.CloseKey(key)
    except Exception:
        scheme = "light"

    _CACHED_SCHEME = scheme
    return scheme


async def apply_native_color_scheme_to_page(page, logger=None):
    """Emulate the host OS color scheme on a single page so the site's own
    ``prefers-color-scheme`` CSS activates naturally."""
    scheme = resolve_os_color_scheme()
    try:
        await page.emulate_media(color_scheme=scheme)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not emulate '{scheme}' color scheme on page: {exc}")


async def apply_native_color_scheme_to_context(context, logger=None):
    """Apply the OS color scheme to every current page in the context, and to any
    page opened later in the same context (e.g. the Bitmoji editor tab)."""
    for page in list(getattr(context, "pages", []) or []):
        await apply_native_color_scheme_to_page(page, logger=logger)

    def _on_new_page(page):
        try:
            asyncio.get_event_loop().create_task(
                apply_native_color_scheme_to_page(page, logger=logger)
            )
        except Exception:
            pass

    try:
        context.on("page", _on_new_page)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not register color-scheme handler on context: {exc}")


# --- Backwards-compatible aliases -------------------------------------------
# These names historically forced dark mode; they now mirror the OS appearance,
# which is the behavior we want everywhere they were used.
apply_dark_mode_to_page = apply_native_color_scheme_to_page
apply_dark_mode_preferences = apply_native_color_scheme_to_context
apply_normal_theme_to_page = apply_native_color_scheme_to_page
apply_normal_theme_preferences = apply_native_color_scheme_to_context
