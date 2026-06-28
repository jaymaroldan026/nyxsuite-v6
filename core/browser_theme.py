_DARK_MODE_INIT_SCRIPT = """
() => {
    try {
        const keys = [
            'theme',
            'color-theme',
            'ui-theme',
            'appearance',
            'mode',
            'snapTheme',
            'colorScheme',
            'prefers-color-scheme',
            'preferred-theme'
        ];
        const styleId = '__nyxify_force_dark_mode';
        const styleContent = `
            :root {
                color-scheme: dark !important;
            }
            html, body {
                background-color: #101317 !important;
                color: #e6ebf0 !important;
                color-scheme: dark !important;
            }
            input, textarea, select, button, [role="button"] {
                color-scheme: dark !important;
            }
            a {
                color: #8ab4f8 !important;
            }
        `;

        const ensureDarkMarkers = () => {
            for (const key of keys) {
                try { localStorage.setItem(key, 'dark'); } catch (_) {}
                try { sessionStorage.setItem(key, 'dark'); } catch (_) {}
            }

            try {
                document.documentElement.setAttribute('data-theme', 'dark');
                document.documentElement.classList.add('dark');
                document.documentElement.style.colorScheme = 'dark';
            } catch (_) {}

            try {
                if (document.body) {
                    document.body.classList.add('dark');
                    document.body.style.colorScheme = 'dark';
                }
            } catch (_) {}

            try {
                let meta = document.querySelector('meta[name="color-scheme"]');
                if (!meta) {
                    meta = document.createElement('meta');
                    meta.name = 'color-scheme';
                    (document.head || document.documentElement).appendChild(meta);
                }
                meta.content = 'dark';
            } catch (_) {}

            try {
                let style = document.getElementById(styleId);
                if (!style) {
                    style = document.createElement('style');
                    style.id = styleId;
                    style.textContent = styleContent;
                    (document.head || document.documentElement).appendChild(style);
                }
            } catch (_) {}
        };

        if (typeof window.matchMedia === 'function' && !window.__nyxifyDarkMediaPatched) {
            const originalMatchMedia = window.matchMedia.bind(window);
            window.matchMedia = (query) => {
                const text = String(query || '');
                if (text.toLowerCase().includes('prefers-color-scheme')) {
                    const matchesDark = text.toLowerCase().includes('dark');
                    return {
                        matches: matchesDark,
                        media: text,
                        onchange: null,
                        addListener() {},
                        removeListener() {},
                        addEventListener() {},
                        removeEventListener() {},
                        dispatchEvent() { return false; },
                    };
                }
                return originalMatchMedia(text);
            };
            window.__nyxifyDarkMediaPatched = true;
        }

        ensureDarkMarkers();

        if (!window.__nyxifyDarkObserver) {
            const observer = new MutationObserver(() => ensureDarkMarkers());
            observer.observe(document.documentElement || document, {
                childList: true,
                subtree: true,
            });
            window.__nyxifyDarkObserver = observer;
        }
    } catch (_) {}
}
"""

_NORMAL_THEME_INIT_SCRIPT = """
() => {
    try {
        const styleId = '__nyxify_force_dark_mode';
        const meta = document.querySelector('meta[name="color-scheme"]');
        const html = document.documentElement;
        const body = document.body;

        try {
            if (window.__nyxifyDarkObserver && typeof window.__nyxifyDarkObserver.disconnect === 'function') {
                window.__nyxifyDarkObserver.disconnect();
            }
            window.__nyxifyDarkObserver = null;
        } catch (_) {}

        try {
            delete window.__nyxifyDarkMediaPatched;
        } catch (_) {
            window.__nyxifyDarkMediaPatched = false;
        }

        const clearStorageKey = (key) => {
            try { localStorage.removeItem(key); } catch (_) {}
            try { sessionStorage.removeItem(key); } catch (_) {}
        };

        [
            'theme',
            'color-theme',
            'ui-theme',
            'appearance',
            'mode',
            'snapTheme',
            'colorScheme',
            'prefers-color-scheme',
            'preferred-theme'
        ].forEach(clearStorageKey);

        try {
            if (html) {
                html.removeAttribute('data-theme');
                html.classList.remove('dark');
                html.style.removeProperty('color-scheme');
            }
        } catch (_) {}

        try {
            if (body) {
                body.classList.remove('dark');
                body.style.removeProperty('color-scheme');
            }
        } catch (_) {}

        try {
            if (meta) {
                meta.content = 'light dark';
            }
        } catch (_) {}

        try {
            const style = document.getElementById(styleId);
            if (style && style.parentNode) {
                style.parentNode.removeChild(style);
            }
        } catch (_) {}
    } catch (_) {}
}
"""


async def apply_dark_mode_to_page(page, logger=None):
    try:
        await page.emulate_media(color_scheme="dark")
    except Exception as exc:
        if logger:
            logger.debug(f"Could not emulate dark color scheme on page: {exc}")

    try:
        await page.add_init_script(_DARK_MODE_INIT_SCRIPT)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not add dark-mode init script to page: {exc}")

    try:
        await page.evaluate(_DARK_MODE_INIT_SCRIPT)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not apply dark-mode script to current page: {exc}")


async def apply_dark_mode_preferences(context, logger=None):
    try:
        await context.add_init_script(_DARK_MODE_INIT_SCRIPT)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not add dark-mode init script to context: {exc}")

    for page in list(getattr(context, "pages", []) or []):
        await apply_dark_mode_to_page(page, logger=logger)


async def apply_normal_theme_to_page(page, logger=None):
    try:
        await page.emulate_media(color_scheme="no-preference")
    except Exception as exc:
        if logger:
            logger.debug(f"Could not restore default color scheme on page: {exc}")

    try:
        await page.evaluate(_NORMAL_THEME_INIT_SCRIPT)
    except Exception as exc:
        if logger:
            logger.debug(f"Could not clear dark-mode script from current page: {exc}")


async def apply_normal_theme_preferences(context, logger=None):
    for page in list(getattr(context, "pages", []) or []):
        await apply_normal_theme_to_page(page, logger=logger)
