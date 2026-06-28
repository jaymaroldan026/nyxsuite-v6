import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright

from core.browser_window import maximize_browser_window
from core.bitmoji.interaction_flow import BannedSnapError, BitmojiInteractionMixin
from core.bitmoji.proxy_failure import BitmojiProxyFailureError
from core.bitmoji.outfit_flow import BitmojiOutfitMixin
from core.nyx_runtime_config import CONFIG_PATH as NYX_CONFIG_PATH, load_nyx_config
from core.bitmoji.save_flow import BitmojiSaveMixin
from snap_selectors.selectors import BITMOJI_SELECTORS

BITMOJI_CREATE_URL = "https://www.bitmoji.com/avatar/create/?require_snapchat"


def _is_manual_browser_close(exc):
    """True when the error means the AdsPower browser/profile was closed out from
    under us mid-run (user manually exited the profile, or AdsPower stopped it).

    Playwright surfaces this as a TargetClosedError or a CDP "connection closed"
    style message once the websocket to the browser drops. Banned and proxy
    failures are caught earlier with their own typed exceptions, so by the time a
    plain close reaches the generic handler it's a manual/forced termination."""
    name = type(exc).__name__.lower()
    if "targetclosed" in name:
        return True
    msg = str(exc or "").lower()
    tokens = (
        "target page, context or browser has been closed",
        "target closed",
        "browser has been closed",
        "browser closed",
        "connection closed",
        "page, context or browser has been closed",
        "websocket connection closed",
    )
    return any(token in msg for token in tokens)

# Same loop-binding fix as core/task_runner.py — lazily build per running loop.
_bitmoji_transition_phase_semaphore: "asyncio.Semaphore | None" = None
_bitmoji_transition_phase_loop = None


def _effective_transition_concurrency():
    """Return the number of concurrent transition-phase slots.

    Priority:
    1. ``BITMOJI_TRANSITION_PHASE_CONCURRENCY`` env var (explicit override).
    2. ``max_parallel_profiles`` from the Nyx runtime config (matches whatever
       the user set in the dashboard — works for any parallelism level).
    3. Fallback: 999 (effectively unlimited) so the semaphore never becomes a
       bottleneck when neither source is available.
    """
    env_val = os.getenv("BITMOJI_TRANSITION_PHASE_CONCURRENCY", "").strip()
    if env_val:
        try:
            return max(1, int(env_val))
        except (ValueError, TypeError):
            pass
    try:
        config = load_nyx_config()
        return max(1, int(config.get("max_parallel_profiles", 999) or 999))
    except Exception:
        return 999


def _transition_phase_semaphore():
    global _bitmoji_transition_phase_semaphore, _bitmoji_transition_phase_loop
    loop = asyncio.get_running_loop()
    if _bitmoji_transition_phase_loop is not loop:
        _bitmoji_transition_phase_semaphore = asyncio.Semaphore(_effective_transition_concurrency())
        _bitmoji_transition_phase_loop = loop
    return _bitmoji_transition_phase_semaphore


class BitmojiCreator(BitmojiInteractionMixin, BitmojiOutfitMixin, BitmojiSaveMixin):
    LOGIN_WITH_SNAPCHAT_SELECTORS = [
        "button:has-text('Log In with Snapchat')",
        "button:has-text('Snapchat')",
        "a:has-text('Snapchat')",
        "[role='button']:has-text('Snapchat')",
    ]

    OAUTH_CONTINUE_SELECTORS = [
        "button.ThemeComponents_continueButton__C1AvV",
        "button[class*='ThemeComponents_continueButton']",
        "button:has-text('Continue')",
        "button:has-text('Agree')",
        "button:has-text('Allow')",
        "button:has-text('Accept')",
        "button:has-text('Authorize')",
        "button:has-text('Continuar')",
        "button:has-text('Aceptar')",
        "button:has-text('Permitir')",
        "button:has-text('Autorizar')",
        "button:has-text('Continua')",
        "button:has-text('ContinuÄƒ')",
        "button:has-text('De acord')",
        "button[type='submit']",
        "input[type='submit']",
    ]

    FEMALE_AVATAR_SELECTORS = [
        ".gender-select button:has(.gender-icon.female)",
        ".gender-select button:nth-of-type(2)",
        "button[aria-label='Female avatar']",
        "button[aria-label='Female Avatar']",
        "button[aria-label*='female' i]",
        "button[aria-label='Avatar femenino']",
        "button[aria-label='Avatar feminin']",
        "button[aria-label='Avatar femeie']",
        "button[aria-label='Avatar feminino']",
        "button[aria-label='Avatar femminile']",
        "button:has(.gender-icon.female)",
        "[role='button']:has(.gender-icon.female)",
        "button:has-text('Female')",
        "button:has-text('Mujer')",
        "button:has-text('Femenino')",
        "button:has-text('Feminino')",
        "button:has-text('Feminin')",
        "button:has-text('Femme')",
        "button:has-text('Donna')",
    ]

    SAVE_BUTTON_SELECTORS = [
        "div.save-button",
        "div[class*='save-button']",
        "button[data-testid*='save']",
        "[role='button'][data-testid*='save']",
    ]

    SAVE_CONFIRM_SELECTORS = [
        "[role='dialog'] button[type='submit']",
        "[role='dialog'] input[type='submit']",
        ".modal button[type='submit']",
        ".modal input[type='submit']",
        "button[type='submit']",
        "input[type='submit']",
    ]

    SAVE_ERROR_SELECTORS = [
        "p.error.subtext",
        "p.subtext.error",
        "[role='dialog'] .error.subtext",
        ".modal .error.subtext",
        "[role='dialog'] p[class*='error']",
        ".modal p[class*='error']",
        "p:has-text('Oops! Something went wrong. Please try again.')",
    ]

    SAVE_CANCEL_SELECTORS = [
        "[role='dialog'] button.button.secondary[type='button']",
        ".modal button.button.secondary[type='button']",
        "[role='dialog'] button[type='button']",
        ".modal button[type='button']",
        "button.button.secondary[type='button']",
    ]

    def __init__(self, ws_endpoint, logger):
        self.ws_endpoint = ws_endpoint
        self.logger = logger
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.last_result = "normal"
        # Live step tracking so a FAILED row keeps the exact step it died on
        # (e.g. "face_hair_style") instead of a generic "bitmoji_failed".
        self.current_step = ""
        self._progress_callback = None
        self.delay_min = float(os.getenv("HUMAN_DELAY_MIN", "0.6"))
        self.delay_max = float(os.getenv("HUMAN_DELAY_MAX", "1.8"))
        self.think_min = float(os.getenv("THINK_DELAY_MIN", "0.2"))
        self.think_max = float(os.getenv("THINK_DELAY_MAX", "0.7"))
        self.profile_jitter = __import__("random").uniform(0.9, 1.15)
        self.automation_speed = 1.0
        self.hair_randomizer_enabled = False
        self._runtime_config_mtime_ns = None
        self.pause_file = Path(__file__).resolve().parents[1] / "logs" / "bot.paused"
        self.page_load_timeout_ms = int(os.getenv("PAGE_LOAD_TIMEOUT_MS", "180000"))
        self.navigation_timeout_ms = int(os.getenv("NAVIGATION_TIMEOUT_MS", "60000"))
        self.long_wait_seconds = int(os.getenv("LONG_WAIT_SECONDS", "120"))
        self.manual_login_wait_seconds = int(os.getenv("MANUAL_LOGIN_WAIT_SECONDS", "1800"))
        self.refresh_runtime_settings(force=True)

    def _get_runtime_config_mtime_ns(self):
        try:
            return NYX_CONFIG_PATH.stat().st_mtime_ns
        except Exception:
            return None

    def refresh_runtime_settings(self, force=False):
        current_mtime_ns = self._get_runtime_config_mtime_ns()
        if not force and current_mtime_ns == self._runtime_config_mtime_ns:
            return False

        runtime_config = load_nyx_config()
        self.automation_speed = float(runtime_config.get("automation_speed", 1.0) or 1.0)
        self.hair_randomizer_enabled = bool(runtime_config.get("hair_randomizer_enabled", False))
        self._runtime_config_mtime_ns = current_mtime_ns
        return True

    def report_step(self, step):
        """Record the current automation step and surface it to the runner so
        the task store's ``last_step`` reflects exactly where work is — and,
        on failure, exactly where it stopped (e.g. ``face_hair_style``)."""
        normalized = str(step or "").strip()
        if not normalized:
            return
        self.current_step = normalized
        callback = getattr(self, "_progress_callback", None)
        if callable(callback):
            try:
                callback(normalized)
            except Exception:
                pass

    @asynccontextmanager
    async def transition_phase_slot(self, phase_name):
        sem = _transition_phase_semaphore()
        if self.logger:
            self.logger.info(f"Waiting for transition slot ({phase_name})")
        await sem.acquire()
        try:
            if self.logger:
                self.logger.info(f"Entered transition slot ({phase_name})")
            yield
        finally:
            sem.release()

    async def start(self):
        if not str(self.ws_endpoint or "").strip():
            raise Exception("AdsPower returned an empty Playwright websocket endpoint.")

        last_error = None
        self.playwright = await async_playwright().start()

        for attempt in range(4):
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(self.ws_endpoint)

                for _ in range(20):
                    if self.browser.contexts:
                        self.context = self.browser.contexts[0]
                        await maximize_browser_window(self.browser, logger=self.logger)
                        return
                    await asyncio.sleep(0.25)

                raise Exception("Connected to browser, but no browser context became ready.")
            except Exception as exc:
                last_error = exc
                if self.logger:
                    self.logger.warning(
                        f"CDP connect retry {attempt + 1}/4 failed for websocket {self.ws_endpoint}: {exc}"
                    )
                await asyncio.sleep(1.0 + (attempt * 0.4))

        raise Exception(f"Could not connect to AdsPower browser via CDP: {last_error}")

    async def stop(self):
        if self.page:
            try:
                if not self.page.is_closed():
                    await self.page.close()
            except Exception:
                pass

        if self.playwright:
            await self.playwright.stop()

    async def human_delay(self, a=None, b=None, *, kind="action", respect_speed=True, respect_jitter=True):
        await self.wait_if_paused()
        self.refresh_runtime_settings()

        if a is None:
            a = self.delay_min if kind == "action" else self.think_min
        if b is None:
            b = self.delay_max if kind == "action" else self.think_max

        low = min(a, b)
        high = max(a, b)

        if respect_jitter:
            low *= self.profile_jitter
            high *= self.profile_jitter

        if respect_speed:
            speed = max(0.1, min(2.0, self.automation_speed))
            low /= speed
            high /= speed

        low = max(0.01, low)
        high = max(low, high)
        total_delay = __import__("random").uniform(low, high)
        elapsed = 0.0

        while elapsed < total_delay:
            await self.wait_if_paused()
            chunk = min(0.25, total_delay - elapsed)
            await asyncio.sleep(chunk)
            elapsed += chunk

    async def wait_if_paused(self):
        while self.pause_file.exists():
            if self.logger:
                self.logger.info("Bot paused during active run")
            await asyncio.sleep(1)

    def resolve_selector(self, selector_key):
        if "." in selector_key:
            group, key = selector_key.split(".", 1)
            if group in BITMOJI_SELECTORS and isinstance(BITMOJI_SELECTORS[group], dict):
                return BITMOJI_SELECTORS[group][key]
        return selector_key

    def parse_nth_selector(self, selector):
        marker = ">> nth="
        if marker not in selector:
            return None, None

        base_selector, nth_value = selector.split(marker, 1)

        try:
            return base_selector.strip(), int(nth_value.strip())
        except ValueError:
            return None, None

    def _get_page_url(self, page):
        try:
            return (page.url or "").strip()
        except Exception:
            return ""

    def _is_noise_page_url(self, url):
        normalized = (url or "").strip().lower()
        return (
            "start.adspower.net" in normalized
            or normalized in {"about:blank", "chrome://newtab/", "chrome://new-tab-page/"}
            or normalized.startswith("chrome://newtab")
        )

    def _is_adspower_start_page_url(self, url):
        normalized = (url or "").strip().lower()
        return "start.adspower.net" in normalized

    def _is_work_page_url(self, url):
        normalized = (url or "").strip().lower()
        if not normalized:
            return False
        return any(
            token in normalized
            for token in [
                "bitmoji.com",
                "snapchat.com",
                "accounts.snapchat.com",
                "chrome://extensions",
            ]
        )

    async def close_noise_pages(self):
        if not self.context:
            return 0

        closed_count = 0
        preserved_adspower_start = False

        for page in list(self.context.pages):
            if self.page is not None and page == self.page:
                continue

            url = self._get_page_url(page)
            if not self._is_noise_page_url(url):
                continue

            if self._is_adspower_start_page_url(url):
                if preserved_adspower_start:
                    should_close = True
                else:
                    preserved_adspower_start = True
                    should_close = False
            else:
                should_close = True

            if not should_close:
                continue

            try:
                if not page.is_closed():
                    await page.close()
                    closed_count += 1
                    if self.logger:
                        self.logger.info(f"Closed stray browser tab before Bitmoji action: {url}")
            except Exception as exc:
                if self.logger:
                    self.logger.warning(f"Could not close stray browser tab {url}: {exc}")

        if self.page is not None and self._is_noise_page_url(self._get_page_url(self.page)):
            self.page = None

        return closed_count

    async def get_candidate_pages(self):
        pages = []

        if self.context:
            pages.extend(self.context.pages)

        if self.page and self.page not in pages:
            pages.append(self.page)

        filtered_pages = []

        for page in pages:
            try:
                if page.is_closed():
                    continue
            except Exception:
                continue

            url = self._get_page_url(page)
            if self._is_noise_page_url(url):
                continue
            if not self._is_work_page_url(url):
                continue
            if page not in filtered_pages:
                filtered_pages.append(page)

        return filtered_pages

    async def get_contexts(self):
        contexts = []

        for page in await self.get_candidate_pages():
            contexts.append(page)
            for frame in page.frames:
                if frame not in contexts:
                    contexts.append(frame)

        return contexts

    async def is_editor_context(self, ctx):
        try:
            if await self.find_save_button_locator(ctx) is not None:
                return True
            if await ctx.locator(
                "img.current_preview, .current_preview, canvas, #current-category, "
                "[class*='traits-container'], [class*='fashion-traits'], [class*='avatar-builder']"
            ).count() > 0:
                return True
            if await ctx.locator(
                ".top-category-container, .category-item, [class*='category-item'], "
                "[class*='subcategory'], [data-testid*='category']"
            ).count() >= 3:
                return True
        except Exception:
            return False
        return False

    async def is_account_home_context(self, ctx):
        try:
            current_url = ""
            try:
                current_url = ctx.url or ""
            except Exception:
                current_url = ""

            if "bitmoji.com/home" in current_url:
                if not await self.is_editor_context(ctx):
                    return True
                if await ctx.locator("main, section, article, nav").count() > 0:
                    return True

            if await ctx.locator("xpath=//h2[normalize-space()='Manage My Account']").count() > 0:
                return True

            heading_texts = await ctx.locator("h2").all_text_contents()
            if any(text.strip() == "Manage My Account" for text in heading_texts):
                return True

            account_links = ctx.locator("a[href*='account'], a[href*='settings'], a[href*='logout']")
            if await account_links.count() > 0 and "bitmoji.com/home" in current_url:
                return True

            return False
        except Exception:
            return False

    async def wait_for_account_home_heading(self, timeout_ms=3000):
        end_time = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)

        while asyncio.get_event_loop().time() < end_time:
            for ctx in await self.get_contexts():
                if await self.is_account_home_context(ctx):
                    return True
            await asyncio.sleep(0.25)

        return False

    async def check_session_state(self, fast=False):
        await self.wait_if_paused()
        if fast:
            await self.human_delay(0.02, 0.05, kind="think", respect_speed=False, respect_jitter=False)
        else:
            await self.human_delay(1.2, 2.0, kind="think")

        if await self.detect_authorization_error():
            print("State: BANNED (Snapchat authorization error)")
            return "BANNED"

        if await self.wait_for_account_home_heading(timeout_ms=1000):
            print("State: ACCOUNT_HOME")
            return "ACCOUNT_HOME"

        for ctx in await self.get_contexts():
            try:
                current_url = ""
                try:
                    current_url = ctx.url or ""
                except Exception:
                    current_url = ""

                if ("bitmoji.com/home" in current_url and await self.is_account_home_context(ctx)) or await self.is_account_home_context(ctx):
                    print("State: ACCOUNT_HOME")
                    return "ACCOUNT_HOME"

                if await self.is_snapchat_login_context(ctx):
                    print("State: LOGIN")
                    return "LOGIN"

                if await self.find_login_with_snapchat_locator(ctx):
                    print("State: LOGIN")
                    return "LOGIN"

                if await self.find_oauth_continue_locator(ctx):
                    print("State: CONTINUE")
                    return "CONTINUE"

                if await self.find_female_avatar_locator(ctx):
                    print("State: GENDER")
                    return "GENDER"
            except Exception:
                continue

        ctx = await self.get_editor_context()
        if ctx and await self.is_editor_context(ctx):
            print("State: EDITOR")
            return "EDITOR"

        # Nothing actionable matched. Before reporting UNKNOWN (which would just
        # spin until the long wait times out), check whether the page is stuck on
        # a profile-proxy failure (Chrome "No internet / ERR_PROXY_CONNECTION_FAILED").
        # The innerText scan only runs in this otherwise-stuck branch so the fast
        # state loop stays cheap on normal pages.
        try:
            if await self.get_bitmoji_proxy_failure_signal():
                print("State: PROXY")
                return "PROXY"
        except Exception:
            pass

        return "UNKNOWN"

    async def wait_for_post_login_state(self, timeout_seconds=None):
        print("Waiting for Bitmoji redirect...")

        if timeout_seconds is None:
            timeout_seconds = self.long_wait_seconds

        for _ in range(int(timeout_seconds)):
            await self.wait_if_paused()
            state = await self.check_session_state(fast=True)

            if state == "BANNED":
                raise BannedSnapError("Snapchat authorization error after login redirect.")

            if state == "PROXY":
                # Profile proxy died mid-auth. Wait ~100s (refreshing) for it to
                # recover; if it returns, resume from whatever state the editor
                # reloads into, otherwise this raises BitmojiProxyFailureError and
                # the runner marks the profile proxy_error and moves on.
                recovered = await self.wait_for_bitmoji_proxy_recovery(BITMOJI_CREATE_URL)
                if recovered in ["GENDER", "EDITOR", "ACCOUNT_HOME"]:
                    print(f"Arrived at: {recovered}")
                    return recovered
                if recovered == "CONTINUE":
                    await self.handle_oauth_continue()
                continue

            if state in ["GENDER", "EDITOR", "ACCOUNT_HOME"]:
                print(f"Arrived at: {state}")
                return state

            await self.human_delay(0.05, 0.12, kind="think", respect_speed=False, respect_jitter=False)

        raise Exception("Timeout after login redirect")

    async def wait_for_editor(self):
        print("Waiting for avatar editor UI...")

        end_time = asyncio.get_event_loop().time() + float(self.long_wait_seconds)
        check_index = 0
        gender_retries = 0
        oauth_retries = 0

        while asyncio.get_event_loop().time() < end_time:
            await self.wait_if_paused()

            try:
                if await self.wait_for_account_home_heading(timeout_ms=250):
                    print("Account home detected while waiting for editor")
                    self.last_result = "already_has_bitmoji"
                    return

                ctx = await self.get_editor_context()
                if ctx and await self.is_editor_context(ctx):
                    print("Editor ready")
                    return
            except Exception:
                pass

            state = "UNKNOWN"
            try:
                state = await self.check_session_state(fast=True)
                if state == "EDITOR":
                    print("Editor ready")
                    return
                if state == "ACCOUNT_HOME":
                    print("Account home detected while waiting for editor")
                    self.last_result = "already_has_bitmoji"
                    return
                if state == "CONTINUE" and oauth_retries < 2:
                    oauth_retries += 1
                    await self.handle_oauth_continue()
                    continue
                if state == "GENDER" and gender_retries < 3:
                    gender_retries += 1
                    await self.select_gender()
                    continue
            except BannedSnapError:
                raise
            except Exception:
                pass

            # Checked outside the swallowing try/except so the banned signal is
            # never lost to a broad `except Exception`.
            if state == "BANNED":
                raise BannedSnapError("Snapchat authorization error while waiting for editor.")

            # Likewise for a proxy failure: kick off the ~100s refresh/recovery
            # OUTSIDE the swallowing try so a real timeout raises
            # BitmojiProxyFailureError (-> proxy_error) instead of being eaten.
            # If the proxy recovers the loop just re-evaluates the reloaded page.
            if state == "PROXY":
                await self.wait_for_bitmoji_proxy_recovery(BITMOJI_CREATE_URL)
                # Proxy recovered (otherwise the call above raised). Give the
                # editor a fresh wait window since recovery may have consumed
                # most of the original one.
                end_time = asyncio.get_event_loop().time() + float(self.long_wait_seconds)
                continue

            if check_index % 10 == 0:
                ctx = await self.get_editor_context()
                current_url = "no-page"
                try:
                    current_url = ctx.url if ctx else (self.page.url if self.page else "no-page")
                except Exception:
                    current_url = self.page.url if self.page else "no-page"
                print(f"[DEBUG] editor check {check_index} -> not ready | state={state} | url={current_url}")

            check_index += 1
            await asyncio.sleep(0.25)

        raise Exception("Editor failed to load")

    async def reconcile_has_bitmoji_result(self, reason=""):
        try:
            state = await self.check_session_state(fast=True)
            if state == "ACCOUNT_HOME":
                self.last_result = "already_has_bitmoji"
                print("Bitmoji account home detected during failure reconciliation")
                return True
        except Exception:
            pass

        try:
            for ctx in await self.get_contexts():
                if await self.is_account_home_context(ctx):
                    self.last_result = "already_has_bitmoji"
                    print("Bitmoji account context confirmed during failure reconciliation")
                    return True
        except Exception:
            pass

        if self.logger and reason:
            self.logger.info(f"Bitmoji reconciliation found no home state ({reason})")

        return False

    async def run(
        self,
        profile_id,
        model,
        outfit_seed="",
        snapchat_credentials=None,
        browser_ready=False,
        progress_callback=None,
        manual_queue_mode=False,
    ):
        try:
            self.last_result = "normal"
            self._progress_callback = progress_callback
            self.refresh_runtime_settings(force=True)
            if not browser_ready:
                await self.start()
            async with self.transition_phase_slot("open_bitmoji_page"):
                state = await self.open_bitmoji_page()
            if not state:
                state = await self.check_session_state(fast=True)

            if state == "BANNED":
                raise BannedSnapError("Snapchat authorization error on Bitmoji open.")

            if state == "LOGIN":
                if callable(progress_callback):
                    progress_callback("need_login")
                auto_login_state = await self.try_auto_snapchat_login(
                    profile_id,
                    credentials=snapchat_credentials,
                    progress_callback=progress_callback,
                )
                if auto_login_state is not None:
                    state = auto_login_state
                else:
                    state = await self.wait_for_manual_login_resume(progress_callback=progress_callback)

            if state == "BANNED":
                raise BannedSnapError("Snapchat authorization error after login.")

            if state == "CONTINUE":
                if callable(progress_callback):
                    progress_callback("authorizing_bitmoji")
                async with self.transition_phase_slot("oauth_continue"):
                    await self.handle_oauth_continue()
                    state = await self.wait_for_post_login_state()

            if state == "ACCOUNT_HOME":
                print("Bitmoji already exists for this account")
                self.last_result = "already_has_bitmoji"
                return True

            if state == "GENDER":
                async with self.transition_phase_slot("gender_editor_handoff"):
                    avatar = self.page.locator("img.current_preview")
                    if await avatar.count() == 0:
                        await self.select_gender()
                    else:
                        print("Skipping gender (editor already loaded)")

                    await self.wait_for_editor()
            else:
                async with self.transition_phase_slot("wait_for_editor"):
                    await self.wait_for_editor()

            if self.last_result == "already_has_bitmoji":
                print("Bitmoji already exists for this account")
                return True

            if callable(progress_callback):
                progress_callback("applying_face_model")
            face_applied = await self.apply_face_model(model, profile_id)
            if not face_applied:
                if await self.reconcile_has_bitmoji_result("face_model_returned_false"):
                    return True
                return False

            print("FACE APPLIED")
            await self.human_delay(0.5, 1.2, kind="think")

            if callable(progress_callback):
                progress_callback("applying_outfit")
            await self.apply_outfit(profile_id, model=model, outfit_seed=outfit_seed)
            if callable(progress_callback):
                progress_callback("outfit_applied")

            print("OUTFIT APPLIED")
            await self.human_delay(0.05, 0.12, kind="think", respect_speed=False, respect_jitter=False)

            if callable(progress_callback):
                progress_callback("saving_bitmoji")
            async with self.transition_phase_slot("save_bitmoji"):
                await self.save_bitmoji()
            if callable(progress_callback):
                progress_callback("completed")
            print("BITMOJI SAVED")
            return True
        except BannedSnapError as exc:
            # Banned/locked account: never retry. Flag it so the runner marks the
            # row banned on SnapBoard and moves on to the next AdsPower profile.
            self.last_result = "banned_snap"
            if self.logger:
                self.logger.warning(f"Banned Snapchat account for profile {profile_id}: {exc}")
            print(f"BANNED SNAP: {exc}")
            return False
        except BitmojiProxyFailureError as exc:
            # Proxy stayed dead through the ~100s refresh window. Never retry —
            # flag it so the runner marks the row's last step proxy_error, closes
            # the AdsPower profile, and moves on to the next account.
            self.last_result = "proxy_error"
            if self.logger:
                self.logger.warning(f"Proxy failure for profile {profile_id}: {exc}")
            print(f"PROXY ERROR: {exc}")
            return False
        except Exception as exc:
            # User closed / exited the AdsPower profile mid-run (or AdsPower
            # stopped it): the browser is gone, so don't retry — flag it so the
            # runner marks the row manual_terminate and moves to the next profile.
            if _is_manual_browser_close(exc):
                self.last_result = "manual_terminate"
                if self.logger:
                    self.logger.warning(
                        f"AdsPower profile {profile_id} closed manually during Bitmoji creation: {exc}"
                    )
                print(f"MANUAL TERMINATE: {exc}")
                return False
            if await self.reconcile_has_bitmoji_result(f"run_exception:{exc}"):
                return True
            raise
        finally:
            await self.stop()
