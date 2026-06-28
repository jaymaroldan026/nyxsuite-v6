import asyncio

SNAPCHAT_SIGNUP_URL = "https://accounts.snapchat.com/v2/signup"
SNAPCHAT_PAGE_READY_TIMEOUT_MS = 120000
SNAPCHAT_POLL_INTERVAL_MS = 500
SNAPCHAT_HANDOFF_TIMEOUT_SECONDS = 300
SNAPCHAT_HANDOFF_LOG_INTERVAL_SECONDS = 30

from playwright.async_api import async_playwright
from core.browser_window import maximize_browser_window
from core.browser_theme import apply_dark_mode_preferences, apply_dark_mode_to_page

KEEP_ENABLED_EXTENSION_TOKENS = (
    "dark reader",
    "dark mode",
    "night eye",
    "night mode",
    "midnight lizard",
    "super dark mode",
    "stylus",
    "stylebot",
    "turn off the lights",
)


async def _is_locator_visible(locator):
    try:
        return await locator.first.is_visible()
    except Exception:
        return False


async def _click_locator_with_fallback(page, locator):
    button = locator.first

    try:
        await button.scroll_into_view_if_needed()
    except Exception:
        pass

    try:
        await button.click()
        return True
    except Exception:
        pass

    try:
        await button.click(force=True)
        return True
    except Exception:
        pass

    try:
        handle = await button.element_handle()
        if handle is not None:
            await page.evaluate("(el) => el.click()", handle)
            return True
    except Exception:
        pass

    return False


async def _is_any_locator_visible(locators):
    for locator in locators:
        if await _is_locator_visible(locator):
            return True
    return False


def _is_snapchat_signup_url(url):
    return "accounts.snapchat.com/v2/signup" in str(url or "")


def _format_context_page_snapshot(context):
    pages = []
    for index, page in enumerate(getattr(context, "pages", []) or []):
        try:
            pages.append(f"{index}:{page.url}")
        except Exception:
            pages.append(f"{index}:<unreadable>")
    return "[" + ", ".join(pages) + "]"


async def _is_snapchat_signup_page_usable(page):
    try:
        if not _is_snapchat_signup_url(page.url):
            return False
    except Exception:
        return False

    try:
        visible_core_fields = 0
        for selector in ("#firstname", "#day", "#year", "#username", "#password"):
            try:
                if await page.locator(selector).first.is_visible():
                    visible_core_fields += 1
            except Exception:
                continue
        if visible_core_fields >= 3:
            return True
    except Exception:
        pass

    try:
        if await page.locator(
            "div[class*='InitialSignupForm_formWrapper'], form[class*='InitialSignupForm_form']"
        ).first.is_visible():
            return True
    except Exception:
        pass

    try:
        if await _is_any_locator_visible(
            [
                page.locator("[data-testid='mwp-cookie-landing-screen']"),
                page.locator("[data-testid='mwp-cookie-modal-body']"),
                page.locator(".cookie-landing-screen"),
                page.locator("[class*='cookie-landing-screen']"),
                page.get_by_role("button", name="Accept All"),
                page.locator("button:has-text('Accept All')"),
            ]
        ):
            return True
    except Exception:
        pass

    return False


async def _wait_for_usable_signup_page(context, preferred_page, logger, profile_id, deadline=None):
    loop = asyncio.get_running_loop()
    if deadline is None:
        deadline = loop.time() + SNAPCHAT_HANDOFF_TIMEOUT_SECONDS
    next_log_at = 0
    last_stage = "waiting_for_signup_page"

    while True:
        now = loop.time()
        if now >= deadline:
            page_snapshot = _format_context_page_snapshot(context)
            raise RuntimeError(
                f"Snapchat signup handoff timed out after {SNAPCHAT_HANDOFF_TIMEOUT_SECONDS}s "
                f"for AdsPower profile {profile_id}. last_stage={last_stage}; pages={page_snapshot}"
            )

        pages = list(getattr(context, "pages", []) or [])
        if preferred_page in pages:
            pages.remove(preferred_page)
            pages.insert(0, preferred_page)

        for page in pages:
            try:
                page_url = str(page.url or "")
            except Exception:
                continue

            if not _is_snapchat_signup_url(page_url):
                continue

            last_stage = f"signup_url_seen:{page_url[:120]}"
            if await _is_snapchat_signup_page_usable(page):
                if logger:
                    logger.info(
                        f"Detected usable Snapchat signup page for AdsPower profile {profile_id}. "
                        f"url={page_url}"
                    )
                return page

        if logger and now >= next_log_at:
            logger.info(
                f"Waiting for Snapchat signup handoff for AdsPower profile {profile_id}. "
                f"pages={_format_context_page_snapshot(context)}"
            )
            next_log_at = now + SNAPCHAT_HANDOFF_LOG_INTERVAL_SECONDS

        await asyncio.sleep(SNAPCHAT_POLL_INTERVAL_MS / 1000)


async def _wait_for_snapchat_signup_ready(signup_page):
    remaining_ms = SNAPCHAT_PAGE_READY_TIMEOUT_MS

    while remaining_ms > 0:
        try:
            await signup_page.wait_for_url("**accounts.snapchat.com/v2/signup*", timeout=min(remaining_ms, 5000))
        except Exception:
            pass

        if _is_snapchat_signup_url(signup_page.url):
            form_visible = False
            cookie_visible = False

            try:
                form_visible = await signup_page.locator(
                    "div[class*='InitialSignupForm_formWrapper'], form[class*='InitialSignupForm_form'], #firstname"
                ).first.is_visible()
            except Exception:
                form_visible = False

            try:
                cookie_visible = await signup_page.locator(
                    "button:has-text('Accept All'), .cookie-landing-screen button:has-text('Accept All'), "
                    "button.sdsm-button.button-compact.button-primary:has-text('Accept All')"
                ).first.is_visible()
            except Exception:
                cookie_visible = False

            if form_visible or cookie_visible:
                return

        await signup_page.wait_for_timeout(SNAPCHAT_POLL_INTERVAL_MS)
        remaining_ms -= SNAPCHAT_POLL_INTERVAL_MS

    raise RuntimeError("Snapchat signup page did not become ready in time.")


async def _accept_snapchat_cookies_if_present(signup_page, logger, profile_id, timeout_ms=SNAPCHAT_PAGE_READY_TIMEOUT_MS):
    remaining_ms = max(500, int(timeout_ms or SNAPCHAT_PAGE_READY_TIMEOUT_MS))
    cookie_seen = False
    clear_polls = 0
    modal_seen_logged = False
    button_seen_logged = False
    candidate_locators = [
        signup_page.locator("xpath=//button[normalize-space(.)='Accept All' or .//span[normalize-space(.)='Accept All']]"),
        signup_page.locator("div[class*='modal-footer'] button.sdsm-button.button-compact.button-primary"),
        signup_page.locator("[data-testid='mwp-cookie-modal-body']").locator("xpath=ancestor::div[contains(@class,'cookie-landing-screen') or contains(@class,'sdsm-modal-content')][1]//button[contains(@class,'button-primary')]"),
        signup_page.locator("button.sdsm-button.button-compact.button-primary:has-text('Accept All')"),
        signup_page.get_by_role("button", name="Accept All"),
        signup_page.locator("button:has-text('Accept All')"),
        signup_page.locator("span:has-text('Accept All')").locator("xpath=ancestor::button[1]"),
    ]
    cookie_modal_locators = [
        signup_page.locator("[data-testid='mwp-cookie-landing-screen']"),
        signup_page.locator("[data-testid='mwp-cookie-modal-body']"),
        signup_page.locator(".cookie-landing-screen"),
        signup_page.locator("[class*='cookie-landing-screen']"),
        signup_page.locator(".sdsm-modal-content"),
    ]
    signup_form = signup_page.locator(
        "div[class*='InitialSignupForm_formWrapper'], form[class*='InitialSignupForm_form'], #firstname"
    ).first
    core_field_locators = [
        signup_page.locator("#firstname"),
        signup_page.locator("#day"),
        signup_page.locator("#year"),
        signup_page.locator("#username"),
        signup_page.locator("#password"),
    ]

    while remaining_ms > 0:
        try:
            if await signup_form.is_visible():
                visible_core_fields = 0
                for locator in core_field_locators:
                    try:
                        if await locator.first.is_visible():
                            visible_core_fields += 1
                    except Exception:
                        continue

                if visible_core_fields >= 3:
                    if logger:
                        logger.info(
                            f"Snapchat signup form is interactive for AdsPower profile {profile_id}. "
                            f"Proceeding without waiting for additional cookie checks. "
                            f"cookie_seen={cookie_seen}, visible_core_fields={visible_core_fields}"
                        )
                    return cookie_seen
        except Exception:
            pass

        cookie_modal_visible = await _is_any_locator_visible(cookie_modal_locators)
        button_visible = await _is_any_locator_visible(candidate_locators)
        button_clicked = False

        if cookie_modal_visible and not modal_seen_logged and logger:
            logger.info(f"Detected Snapchat cookie modal for AdsPower profile {profile_id}.")
            modal_seen_logged = True

        if button_visible and not button_seen_logged and logger:
            logger.info(f"Detected Snapchat 'Accept All' button for AdsPower profile {profile_id}.")
            button_seen_logged = True

        for locator in candidate_locators:
            try:
                button = locator.first
                button_text = ""
                try:
                    button_text = ((await button.inner_text()) or "").strip()
                except Exception:
                    button_text = ""

                if not await button.is_visible():
                    continue

                if button_text and "accept all" not in button_text.lower():
                    continue

                cookie_seen = True

                if not await _click_locator_with_fallback(signup_page, locator):
                    continue

                button_clicked = True

                await signup_page.wait_for_timeout(750)

                if not await _is_any_locator_visible(cookie_modal_locators) and not await _is_locator_visible(locator):
                    if logger:
                        logger.info(f"Accepted Snapchat cookie popup for AdsPower profile {profile_id}.")
                    return True
            except Exception:
                continue

        if not button_clicked:
            try:
                clicked_via_dom = await signup_page.evaluate(
                    """
                    () => {
                        const candidates = Array.from(document.querySelectorAll('button'));
                        const button = candidates.find((node) => (node.innerText || node.textContent || '').trim().toLowerCase() === 'accept all');
                        if (!button) {
                            return false;
                        }
                        button.click();
                        return true;
                    }
                    """
                )
                if clicked_via_dom:
                    cookie_seen = True
                    await signup_page.wait_for_timeout(750)
                    if not await _is_any_locator_visible(cookie_modal_locators):
                        if logger:
                            logger.info(f"Accepted Snapchat cookie popup for AdsPower profile {profile_id} via DOM fallback.")
                        return True
            except Exception:
                pass

        try:
            if await signup_form.is_visible():
                cookie_still_visible = await _is_any_locator_visible(cookie_modal_locators)

                if not cookie_still_visible:
                    clear_polls += 1
                else:
                    clear_polls = 0

                if clear_polls >= 6:
                    if logger:
                        logger.info(
                            f"{'Cookie popup did not appear' if not cookie_seen else 'Cookie popup no longer blocks the page'} "
                            f"for AdsPower profile {profile_id}."
                        )
                    return cookie_seen
        except Exception:
            pass

        try:
            await signup_page.wait_for_timeout(SNAPCHAT_POLL_INTERVAL_MS)
        except Exception as exc:
            raise RuntimeError(
                f"Snapchat cookie handling interrupted because the page closed for AdsPower profile {profile_id}: {exc}"
            ) from exc
        remaining_ms -= SNAPCHAT_POLL_INTERVAL_MS

    if logger:
        logger.warning(
            f"Snapchat cookie handling timed out for AdsPower profile {profile_id}. "
            f"cookie_seen={cookie_seen}, final_url={signup_page.url}"
        )
    return cookie_seen


async def _open_snapchat_signup_in_new_tab(context, logger, profile_id):
    handoff_deadline = asyncio.get_running_loop().time() + SNAPCHAT_HANDOFF_TIMEOUT_SECONDS
    signup_page = await context.new_page()
    await apply_dark_mode_to_page(signup_page, logger=logger)

    try:
        await signup_page.bring_to_front()
    except Exception:
        pass

    try:
        remaining_ms = max(1000, int((handoff_deadline - asyncio.get_running_loop().time()) * 1000))
        await signup_page.goto(SNAPCHAT_SIGNUP_URL, wait_until="commit", timeout=min(45000, remaining_ms))
    except Exception as exc:
        current_url = str(signup_page.url or "")
        if logger:
            logger.warning(
                f"Snapchat signup navigation raised for AdsPower profile {profile_id}. "
                f"Continuing handoff watcher so manual refresh can recover. "
                f"current_url={current_url}, error={exc}"
            )

    signup_page = await _wait_for_usable_signup_page(
        context,
        signup_page,
        logger,
        profile_id,
        deadline=handoff_deadline,
    )
    cookies_accepted = await _accept_snapchat_cookies_if_present(signup_page, logger, profile_id, timeout_ms=5000)

    try:
        await signup_page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception as exc:
        if logger:
            logger.warning(
                f"Snapchat domcontentloaded wait timed out for AdsPower profile {profile_id}. "
                f"Continuing because the page is already interactive enough. error={exc}"
            )

    # Do not block on networkidle here. Snapchat is interactive before it settles,
    # and waiting for networkidle delays the fill while the page is already usable.
    await signup_page.wait_for_timeout(500)

    cookies_accepted = (
        await _accept_snapchat_cookies_if_present(signup_page, logger, profile_id, timeout_ms=2500)
        or cookies_accepted
    )

    final_url = signup_page.url
    if not _is_snapchat_signup_url(final_url):
        raise RuntimeError(f"New-tab signup navigation did not land on Snapchat signup. Final URL: {final_url}")

    if logger:
        logger.info(
            f"Opened Snapchat signup page for AdsPower profile {profile_id} in a new tab. "
            f"final_url={final_url}, cookies_accepted={cookies_accepted}"
        )

    return {
        "url": final_url,
        "method": "new_tab",
        "cookies_accepted": cookies_accepted,
        "page": signup_page,
    }


async def _open_snapchat_signup_with_timeout(context, logger, profile_id):
    return await _open_snapchat_signup_in_new_tab(context, logger, profile_id)


async def disable_profile_extensions(adspower, profile_id, logger, keep_open=True, keep_playwright=False):
    normalized_profile_id = str(profile_id or "").strip()
    if not normalized_profile_id:
        raise ValueError("AdsPower profile id is required.")

    ws_endpoint = await asyncio.to_thread(adspower.open_profile, normalized_profile_id)
    playwright = await async_playwright().start()
    browser = None

    try:
        browser = await playwright.chromium.connect_over_cdp(ws_endpoint)

        context = None
        for _ in range(20):
            if browser.contexts:
                context = browser.contexts[0]
                break
            await asyncio.sleep(0.25)

        if context is None:
            raise RuntimeError("Connected to AdsPower browser, but no context became available.")

        await maximize_browser_window(browser, logger=logger)
        await apply_dark_mode_preferences(context, logger=logger)

        page = await context.new_page()
        await apply_dark_mode_to_page(page, logger=logger)
        await page.goto("chrome://extensions/", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        last_result = None

        for attempt in range(6):
            result = await page.evaluate(
                """
                (keepEnabledTokens) => {
                    const visited = new Set();

                    function walk(node, visitor) {
                        if (!node || visited.has(node)) {
                            return;
                        }
                        visited.add(node);
                        visitor(node);

                        const children = node.querySelectorAll ? node.querySelectorAll('*') : [];
                        for (const child of children) {
                            if (child.shadowRoot) {
                                walk(child.shadowRoot, visitor);
                            }
                        }
                    }

                    function findExtensionItems() {
                        const items = [];
                        walk(document, (node) => {
                            if (node.querySelectorAll) {
                                for (const item of node.querySelectorAll('extensions-item')) {
                                    items.push(item);
                                }
                            }
                        });
                        return items;
                    }

                    function readToggleState(toggle) {
                        if (!toggle) {
                            return false;
                        }
                        if (typeof toggle.checked === 'boolean') {
                            return toggle.checked;
                        }
                        const ariaPressed = toggle.getAttribute('aria-pressed');
                        if (ariaPressed === 'true' || ariaPressed === 'false') {
                            return ariaPressed === 'true';
                        }
                        return toggle.hasAttribute('checked');
                    }

                    function readItemMetadata(item, root) {
                        const data = item && typeof item === 'object'
                            ? (item.data || item.item || item.extensionInfo || item.extensionData || null)
                            : null;
                        const descriptionNode =
                            root.querySelector('#description') ||
                            root.querySelector('[id="description"]') ||
                            root.querySelector('.description');
                        const textContent = String((root && root.textContent) || '').trim();

                        return {
                            type: String(
                                (data && (data.type || data.appType || data.extensionType || data.kind)) ||
                                item.getAttribute('type') ||
                                item.getAttribute('data-type') ||
                                ''
                            ).trim().toLowerCase(),
                            description: String((descriptionNode && descriptionNode.textContent) || '').trim().toLowerCase(),
                            text: textContent.toLowerCase(),
                        };
                    }

                    function isThemeItem(metadata) {
                        const type = String(metadata && metadata.type || '').trim().toLowerCase();
                        const description = String(metadata && metadata.description || '').trim().toLowerCase();
                        const text = String(metadata && metadata.text || '').trim().toLowerCase();
                        return (
                            type.includes('theme')
                            || description.includes('theme')
                            || text.includes(' theme ')
                            || text.includes('browser theme')
                            || text.includes('chrome theme')
                            || text.includes('appearance')
                        );
                    }

                    function shouldKeepEnabled(name) {
                        const normalized = String(name || '').trim().toLowerCase();
                        if (!normalized) {
                            return false;
                        }

                        if (keepEnabledTokens.some((token) => normalized.includes(token))) {
                            return true;
                        }

                        return (
                            (normalized.includes('dark') && (normalized.includes('mode') || normalized.includes('theme') || normalized.includes('reader'))) ||
                            (normalized.includes('night') && (normalized.includes('mode') || normalized.includes('theme')))
                        );
                    }

                    const disabledNow = [];
                    const alreadyDisabled = [];
                    const missingToggle = [];
                    const keptEnabled = [];

                    for (const item of findExtensionItems()) {
                        const root = item.shadowRoot;
                        if (!root) {
                            continue;
                        }

                        const nameNode =
                            root.querySelector('#name') ||
                            root.querySelector('.title') ||
                            root.querySelector('[id="name"]');
                        const name = (nameNode && nameNode.textContent || '').trim() || 'Unknown extension';
                        const metadata = readItemMetadata(item, root);
                        const toggle =
                            root.querySelector('#enableToggle') ||
                            root.querySelector('cr-toggle');

                        if (!toggle) {
                            missingToggle.push(name);
                            continue;
                        }

                        if (readToggleState(toggle)) {
                            if (shouldKeepEnabled(name) || isThemeItem(metadata)) {
                                keptEnabled.push(name);
                                continue;
                            }
                            toggle.click();
                            disabledNow.push(name);
                        } else {
                            alreadyDisabled.push(name);
                        }
                    }

                    const remainingEnabled = [];
                    for (const item of findExtensionItems()) {
                        const root = item.shadowRoot;
                        if (!root) {
                            continue;
                        }
                        const toggle =
                            root.querySelector('#enableToggle') ||
                            root.querySelector('cr-toggle');
                        const nameNode =
                            root.querySelector('#name') ||
                            root.querySelector('.title') ||
                            root.querySelector('[id="name"]');
                        const name = (nameNode && nameNode.textContent || '').trim() || 'Unknown extension';
                        const metadata = readItemMetadata(item, root);
                        if (toggle && readToggleState(toggle) && !shouldKeepEnabled(name) && !isThemeItem(metadata)) {
                            remainingEnabled.push(name);
                        }
                    }

                    return {
                        disabled_now: disabledNow,
                        already_disabled: alreadyDisabled,
                        missing_toggle: missingToggle,
                        kept_enabled: keptEnabled,
                        remaining_enabled: remainingEnabled,
                        item_count: findExtensionItems().length,
                    };
                }
                """,
                list(KEEP_ENABLED_EXTENSION_TOKENS),
            )

            last_result = result

            if result.get("item_count", 0) <= 0:
                await page.wait_for_timeout(1000)
                continue

            if not result.get("remaining_enabled"):
                if logger:
                    logger.info(
                        f"Disabled AdsPower profile extensions for {normalized_profile_id}: "
                        f"disabled_now={result.get('disabled_now', [])}, "
                        f"already_disabled={result.get('already_disabled', [])}, "
                        f"kept_enabled={result.get('kept_enabled', [])}"
                    )
                signup_result = await _open_snapchat_signup_with_timeout(
                    context, logger, normalized_profile_id
                )
                payload = {
                    "profile_id": normalized_profile_id,
                    "ws_endpoint": ws_endpoint,
                    "disabled_now": result.get("disabled_now", []),
                    "already_disabled": result.get("already_disabled", []),
                    "missing_toggle": result.get("missing_toggle", []),
                    "kept_enabled": result.get("kept_enabled", []),
                    "remaining_enabled": [],
                    "signup_url": signup_result.get("url"),
                    "signup_method": signup_result.get("method"),
                    "signup_page": signup_result.get("page"),
                    "context": context,
                    "playwright_instance": playwright if keep_playwright else None,
                    "success": True,
                }
                if keep_playwright:
                    # Caller owns playwright lifetime — do NOT stop it in finally
                    playwright = None
                return payload

            await page.wait_for_timeout(800)

        remaining_enabled = (last_result or {}).get("remaining_enabled", [])
        if remaining_enabled:
            raise RuntimeError(
                "Some Chrome extensions remained enabled after automation: "
                + ", ".join(remaining_enabled)
            )

        if logger:
            logger.warning(
                f"AdsPower extension cleanup finished without a strict DOM verification for {normalized_profile_id}. "
                f"Treating as success because no enabled extensions were detected. "
                f"last_result={last_result}"
            )

        signup_result = await _open_snapchat_signup_with_timeout(
            context, logger, normalized_profile_id
        )
        payload = {
            "profile_id": normalized_profile_id,
            "ws_endpoint": ws_endpoint,
            "disabled_now": (last_result or {}).get("disabled_now", []),
            "already_disabled": (last_result or {}).get("already_disabled", []),
            "missing_toggle": (last_result or {}).get("missing_toggle", []),
            "kept_enabled": (last_result or {}).get("kept_enabled", []),
            "remaining_enabled": [],
            "signup_url": signup_result.get("url"),
            "signup_method": signup_result.get("method"),
            "signup_page": signup_result.get("page"),
            "context": context,
            "playwright_instance": playwright if keep_playwright else None,
            "success": True,
            "verified": False,
        }
        if keep_playwright:
            playwright = None
        return payload
    finally:
        if browser and not keep_open:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
