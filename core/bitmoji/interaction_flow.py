import asyncio
import random
import re

from core.bitmoji.proxy_failure import (
    BitmojiProxyFailureError,
    detect_proxy_failure_signal,
    select_proxy_failure_recovery,
)


# Snapchat's OAuth screen shows this when the linked account is banned/locked:
# "Authorization Error / Failed to load authorization data". The account can
# never authorize Bitmoji, so we stop, mark it banned, and move on.
AUTHORIZATION_ERROR_TOKENS = (
    "failed to load authorization data",
    "authorization error",
)


class BannedSnapError(Exception):
    """Raised when the Bitmoji flow detects a banned/locked Snapchat account
    (Snapchat OAuth ``Authorization Error``). The runner marks the row banned on
    SnapBoard and proceeds to the next AdsPower profile instead of retrying."""


class BitmojiInteractionMixin:
    async def detect_authorization_error(self):
        """True when a Snapchat OAuth authorization-error page is showing.

        The error renders on ``accounts.snapchat.com`` as a top-level page, so we
        only scan candidate pages (not every frame) to keep this cheap enough to
        call inside the editor/login wait loops."""
        try:
            pages = await self.get_candidate_pages()
        except Exception:
            return False

        for page in pages:
            try:
                url = (self._get_page_url(page) or "").lower()
            except Exception:
                url = ""

            if "snapchat.com" not in url:
                continue

            try:
                text = (await self.get_context_text(page) or "").lower()
            except Exception:
                text = ""

            if not text:
                continue

            if "failed to load authorization data" in text:
                return True
            if "authorization error" in text and "oauth" in url:
                return True

        return False

    async def first_actionable_locator(self, locator, max_candidates=12):
        try:
            count = await locator.count()
        except Exception:
            return None

        if count <= 0:
            return None

        for index in range(min(count, max_candidates)):
            candidate = locator.nth(index)
            try:
                if await candidate.is_visible():
                    return candidate
            except Exception:
                continue

        try:
            return locator.first
        except Exception:
            return None

    async def find_first_visible_locator(self, ctx, selectors):
        for selector in selectors:
            try:
                locator = ctx.locator(selector)
                actionable = await self.first_actionable_locator(locator)
                if actionable is not None:
                    return actionable
            except Exception:
                continue
        return None

    async def find_login_with_snapchat_locator(self, ctx):
        return await self.find_first_visible_locator(ctx, self.LOGIN_WITH_SNAPCHAT_SELECTORS)

    async def is_snapchat_login_context(self, ctx):
        try:
            current_url = (ctx.url or "").lower()
        except Exception:
            current_url = ""

        if "accounts.snapchat.com" not in current_url:
            return False

        if "/v2/login" in current_url or "/accounts/v2/login" in current_url:
            return True

        try:
            heading = ctx.locator("h1")
            if await heading.count() > 0:
                heading_text = (await heading.first.text_content() or "").strip().lower()
                if "log in to snapchat" in heading_text or "enter password" in heading_text:
                    return True
        except Exception:
            pass

        try:
            if await ctx.locator("#username, input[name='accountIdentifier'], #password, input[name='password']").count() > 0:
                return True
        except Exception:
            pass

        return False

    async def get_snapchat_login_context(self):
        for ctx in await self.get_contexts():
            try:
                if await self.is_snapchat_login_context(ctx):
                    return ctx
            except Exception:
                continue
        return None

    async def get_context_text(self, ctx):
        try:
            return await ctx.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            return ""

    async def get_bitmoji_proxy_failure_signal(self, extra_error=""):
        signal = detect_proxy_failure_signal(error=extra_error)
        if signal:
            return signal

        pages = []
        if self.context:
            pages.extend(self.context.pages)
        if self.page and self.page not in pages:
            pages.append(self.page)

        contexts = []
        for page in pages:
            try:
                if page.is_closed():
                    continue
            except Exception:
                continue

            contexts.append(page)
            try:
                for frame in page.frames:
                    if frame not in contexts:
                        contexts.append(frame)
            except Exception:
                pass

        for ctx in contexts:
            try:
                url = ctx.url or ""
            except Exception:
                url = ""

            text = ""
            try:
                text = await ctx.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:
                pass

            signal = detect_proxy_failure_signal(url=url, text=text)
            if signal:
                return signal

        return ""

    async def wait_for_bitmoji_proxy_recovery(self, target_url, initial_signal=""):
        recovery = await asyncio.to_thread(select_proxy_failure_recovery)
        timeout_seconds = int(recovery["timeout_seconds"])
        failure_kind = str(recovery["failure_kind"])
        host_online = bool(recovery["host_online"])
        loop = asyncio.get_event_loop()
        deadline = loop.time() + float(timeout_seconds)
        retry_interval = 30.0
        log_interval = 30.0
        next_retry_at = loop.time()
        next_log_at = loop.time()
        last_signal = initial_signal or await self.get_bitmoji_proxy_failure_signal()

        if self.logger:
            self.logger.warning(
                "Bitmoji proxy failure detected; waiting up to "
                f"{timeout_seconds}s before marking proxy_error. "
                f"kind={failure_kind}; host_online={host_online}; signal={last_signal or 'unknown'}"
            )

        while loop.time() < deadline:
            await self.wait_if_paused()

            try:
                state = await self.wait_for_initial_page_signal(
                    timeout_ms=1500,
                    detect_proxy_failure=False,
                )
                # A genuine recovery is a *real* page state. When the page is still
                # stuck on the proxy-failure page, wait_for_initial_page_signal
                # falls through to check_session_state() and returns "PROXY" — the
                # failure state itself. Treating that as "recovered" returns
                # immediately, and wait_for_editor() then resets its deadline, so
                # the run livelocks forever (proxy detected -> false recovery ->
                # repeat) and the profile never frees its slot. Only break out on a
                # state that actually means the page moved on.
                if state and state not in ("PROXY", "UNKNOWN"):
                    if self.logger:
                        self.logger.info(
                            f"Bitmoji proxy failure recovered before timeout; continuing with state={state}"
                        )
                    return state
            except Exception:
                pass

            signal = await self.get_bitmoji_proxy_failure_signal()
            if signal:
                last_signal = signal

            now = loop.time()
            remaining_seconds = max(0, int(deadline - now))

            if self.logger and now >= next_log_at:
                self.logger.warning(
                    "Bitmoji proxy failure still blocking page; "
                    f"{remaining_seconds}s left before proxy_error. "
                    f"kind={failure_kind}; host_online={host_online}; signal={last_signal or 'unknown'}"
                )
                next_log_at = now + log_interval

            if now >= next_retry_at:
                try:
                    if self.page is None or self.page.is_closed():
                        self.page = await self.context.new_page()
                    await self.page.goto(
                        target_url,
                        timeout=min(30000, max(1000, int((deadline - now) * 1000))),
                        wait_until="domcontentloaded",
                    )
                except Exception as exc:
                    signal = await self.get_bitmoji_proxy_failure_signal(extra_error=str(exc))
                    if signal:
                        last_signal = signal
                    elif not last_signal:
                        last_signal = str(exc)
                next_retry_at = loop.time() + retry_interval

            await asyncio.sleep(min(2.0, max(0.2, deadline - loop.time())))

        raise BitmojiProxyFailureError(
            "Bitmoji proxy failure persisted for "
            f"{timeout_seconds}s; marking profile as proxy_error. "
            f"kind={failure_kind}; host_online={host_online}; Last signal: {last_signal or 'unknown'}"
        )

    async def extract_snapchat_username_from_browser_context(self):
        candidates = []

        if self.page is not None:
            candidates.append(self.page)

        if self.context:
            for page in self.context.pages:
                if page not in candidates:
                    candidates.append(page)

        for page in candidates:
            try:
                dom_username = await page.evaluate(
                    """() => {
                        const normalize = (value) => String(value || '').trim();
                        const extract = (raw) => {
                            const text = normalize(raw);
                            const match = text.match(/^snapchat\\s*:\\s*([A-Za-z0-9._-]{3,32})$/i);
                            return match ? match[1] : '';
                        };

                        const rows = Array.from(document.querySelectorAll('div'));
                        for (const row of rows) {
                            const label = row.querySelector('._cell__label_nnaai_15');
                            const content = row.querySelector('._cell__content_nnaai_23');
                            if (!label || !content) {
                                continue;
                            }

                            if (normalize(label.textContent).toLowerCase() !== 'name') {
                                continue;
                            }

                            const username = extract(content.textContent);
                            if (username) {
                                return username;
                            }
                        }

                        const genericLabels = Array.from(document.querySelectorAll('*')).filter((el) =>
                            normalize(el.textContent).toLowerCase() === 'name'
                        );

                        for (const label of genericLabels) {
                            const row = label.parentElement;
                            if (!row) {
                                continue;
                            }

                            const content = row.querySelector('._cell__content_nnaai_23') || label.nextElementSibling;
                            const username = extract(content?.textContent || '');
                            if (username) {
                                return username;
                            }
                        }

                        return '';
                    }"""
                )
            except Exception:
                dom_username = ""

            if dom_username and re.fullmatch(r"[A-Za-z0-9._-]{3,32}", dom_username):
                if self.logger:
                    self.logger.info(f"Resolved Snapchat username from AdsPower page DOM: {dom_username}")
                return dom_username

            try:
                title = (await page.title() or "").strip()
            except Exception:
                title = ""

            if not title:
                continue

            match = re.match(r"^\s*snapchat\s*:\s*(.+?)\s*$", title, flags=re.IGNORECASE)
            if not match:
                continue

            username = match.group(1).strip().lstrip("@")
            if username and re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
                if self.logger:
                    self.logger.info(f"Resolved Snapchat username from AdsPower tab title: {username}")
                return username

        return ""

    async def detect_snapchat_login_page_state(self, ctx=None):
        target = ctx or await self.get_snapchat_login_context()
        state = {
            "page_type": "unknown",
            "needs_username": False,
            "needs_password": False,
            "is_banned": False,
            "is_inaccessible": False,
            "inaccessible_reason": "",
            "needs_verification": False,
            "is_logged_in": False,
            "error_message": "",
            "url": "",
        }

        if target is None:
            return state

        try:
            state["url"] = (target.url or "").strip()
        except Exception:
            state["url"] = ""

        lower_url = state["url"].lower()
        page_text = (await self.get_context_text(target) or "").strip()
        lower_text = page_text.lower()

        has_username_input = False
        has_password_input = False

        try:
            has_username_input = await target.locator(
                "#username, input[name='accountIdentifier'], input[name='usernameOrEmail']"
            ).count() > 0
        except Exception:
            pass

        try:
            has_password_input = await target.locator(
                "#password, input[name='password'], input[type='password']"
            ).count() > 0
        except Exception:
            pass

        if "/v2/welcome" in lower_url or "/accounts/v2/welcome" in lower_url:
            state["page_type"] = "welcome"
            state["is_logged_in"] = True
            return state

        if has_username_input or "log in to snapchat" in lower_text:
            state["page_type"] = "login_username"
            state["needs_username"] = True

        if has_password_input or "enter password" in lower_text:
            state["page_type"] = "login_password"
            state["needs_password"] = True

        if any(token in lower_url for token in ["/v2/tiv", "/accounts/v2/tiv", "/accounts/verify"]):
            state["needs_verification"] = True
            state["page_type"] = "verification"
        if "confirm it's you" in lower_text or "open the following" in lower_text:
            state["needs_verification"] = True
            state["page_type"] = "verification"

        banned_indicators = [
            "your account is locked",
            "your account has been locked",
            "account is permanently banned",
            "your account has been permanently locked",
            "this account has been suspended",
            "your account has been suspended",
            "account has been terminated",
            "violating our terms of service",
            "violated our community guidelines",
        ]
        if not has_username_input and not has_password_input:
            if any(indicator in lower_text for indicator in banned_indicators):
                state["is_banned"] = True
                state["page_type"] = "banned"

        try:
            error_locator = target.locator("p[data-testid='error-text']").first
            if await error_locator.count() > 0:
                error_text = (await error_locator.text_content() or "").strip()
                if error_text:
                    state["error_message"] = error_text
                    error_lower = error_text.lower()
                    if "temporarily disabled" in error_lower:
                        state["is_inaccessible"] = True
                        state["inaccessible_reason"] = "temporarily disabled"
                    elif "incorrect password" in error_lower:
                        state["is_inaccessible"] = True
                        state["inaccessible_reason"] = "incorrect password"
        except Exception:
            pass

        return state

    async def type_like_human(self, locator, value, *, per_char_delay=(0.08, 0.18)):
        text = str(value or "")
        try:
            await locator.wait_for(state="visible", timeout=10000)
        except Exception:
            pass

        await locator.click()
        element_handle = await locator.element_handle()

        if element_handle is None:
            raise Exception("Could not resolve login input element handle.")

        page = locator.page
        await page.evaluate(
            """(element) => {
                element.focus();
                element.click();
            }""",
            element_handle,
        )

        # Clear the field reliably: select-all + delete, then backspace any
        # leftover characters one at a time. A lone Ctrl+A + Backspace often
        # leaves part of the old value behind on React inputs, so the new text
        # ends up appended to the old.
        try:
            await locator.press("End")
            await self.human_delay(0.04, 0.10, kind="think")
            await locator.press("Control+A")
            await self.human_delay(0.06, 0.12, kind="think")
            await locator.press("Delete")
            await self.human_delay(0.06, 0.14, kind="think")
            for _ in range(4):
                try:
                    remaining = str(await locator.input_value() or "")
                except Exception:
                    remaining = ""
                if not remaining:
                    break
                await locator.press("End")
                for _ in range(len(remaining) + 2):
                    await locator.press("Backspace")
                    await self.human_delay(0.03, 0.09, kind="think")
        except Exception:
            try:
                await locator.fill("")
            except Exception:
                pass

        if text:
            for index, char in enumerate(text):
                await page.keyboard.type(char, delay=random.randint(45, 115))
                await self.human_delay(per_char_delay[0], per_char_delay[1], kind="think")

                if index and index % random.randint(4, 7) == 0:
                    await self.human_delay(0.12, 0.28, kind="think")

        field_value = ""
        try:
            field_value = await locator.input_value()
        except Exception:
            pass

        if field_value != text:
            try:
                await page.evaluate(
                    """({ element, nextValue }) => {
                        const applyValue = (input, value) => {
                            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                            if (setter) {
                                setter.call(input, value);
                            } else {
                                input.value = value;
                            }
                        };

                        const input = element;
                        input.focus();
                        applyValue(input, nextValue);
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return input.value;
                    }""",
                    {"element": element_handle, "nextValue": text},
                )
                field_value = await locator.input_value()
            except Exception:
                pass

        if field_value != text:
            try:
                await locator.press("Control+A")
                await locator.press("Backspace")
                await locator.type(text, delay=max(25, int(per_char_delay[0] * 1000)))
                field_value = await locator.input_value()
            except Exception:
                pass

        if field_value != text:
            raise Exception(f"Input fill verification failed. Expected '{text}' but saw '{field_value}'.")

    async def click_first_available(self, ctx, selectors):
        locator = await self.find_first_visible_locator(ctx, selectors)
        if locator is None:
            return False

        try:
            await locator.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            await locator.click()
        except Exception:
            await locator.click(force=True)
        return True

    async def try_auto_snapchat_login(self, profile_id, credentials=None, progress_callback=None):
        username = str((credentials or {}).get("username", "") or "").strip()
        password = str((credentials or {}).get("password", "") or "").strip()

        if not username:
            username = await self.extract_snapchat_username_from_browser_context()

        if not username or not password:
            if self.logger:
                self.logger.info(
                    f"No Snapchat auto-login credentials resolved for {profile_id}; "
                    f"username={'yes' if username else 'no'} password={'yes' if password else 'no'}; "
                    "falling back to manual login"
                )
            return None

        login_ctx = await self.get_snapchat_login_context()
        if login_ctx is None:
            return None

        if callable(progress_callback):
            progress_callback("auto_login_snapchat")

        if self.logger:
            self.logger.info(
                f"Attempting Snapchat auto-login for {profile_id} using {credentials.get('source', 'unknown')}"
            )

        submit_selectors = [
            "button[data-testid='password-submit-button']",
            "button[type='submit']",
            "button[class*='Login_next']",
            "input[type='submit']",
        ]

        for _ in range(3):
            login_ctx = await self.get_snapchat_login_context()
            page_state = await self.detect_snapchat_login_page_state(login_ctx)

            if page_state["is_banned"]:
                raise Exception("Snapchat account appears banned/locked on login page.")
            if page_state["is_inaccessible"]:
                reason = page_state["inaccessible_reason"] or page_state["error_message"] or "inaccessible"
                raise Exception(f"Snapchat login blocked: {reason}")
            if page_state["needs_verification"]:
                raise Exception("Snapchat login requires verification.")
            if page_state["is_logged_in"]:
                return await self.wait_for_post_login_state(timeout_seconds=20)

            if page_state["needs_username"]:
                username_locator = login_ctx.locator(
                    "input#username[name='accountIdentifier'], #username, input[name='accountIdentifier'], input[name='usernameOrEmail']"
                ).first
                if await username_locator.count() == 0:
                    break
                await self.type_like_human(username_locator, username)
                await self.human_delay(0.25, 0.45, kind="think")
                if not await self.click_first_available(login_ctx, submit_selectors):
                    raise Exception("Could not submit Snapchat username step.")
                await self.human_delay(1.8, 2.6, kind="think")
                continue

            if page_state["needs_password"]:
                password_locator = login_ctx.locator(
                    "input#password[name='password'], #password, input[name='password'], input[type='password']"
                ).first
                if await password_locator.count() == 0:
                    break
                await self.type_like_human(password_locator, password, per_char_delay=(0.09, 0.2))
                await self.human_delay(0.3, 0.55, kind="think")
                if not await self.click_first_available(login_ctx, submit_selectors):
                    raise Exception("Could not submit Snapchat password step.")
                await self.human_delay(2.0, 3.0, kind="think")

                for _ in range(20):
                    follow_state = await self.check_session_state(fast=True)
                    if follow_state in {"CONTINUE", "GENDER", "EDITOR", "ACCOUNT_HOME"}:
                        return follow_state

                    login_ctx = await self.get_snapchat_login_context()
                    if login_ctx is not None:
                        page_state = await self.detect_snapchat_login_page_state(login_ctx)
                        if page_state["is_banned"]:
                            raise Exception("Snapchat account appears banned/locked after password submit.")
                        if page_state["is_inaccessible"]:
                            reason = page_state["inaccessible_reason"] or page_state["error_message"] or "inaccessible"
                            raise Exception(f"Snapchat login failed: {reason}")
                        if page_state["needs_verification"]:
                            raise Exception("Snapchat login requires verification.")

                    await self.human_delay(0.35, 0.65, kind="think")
                break

            break

        if self.logger:
            self.logger.warning(f"Snapchat auto-login did not complete for {profile_id}; falling back to manual login")
        return None

    async def find_oauth_continue_locator(self, ctx):
        locator = await self.find_first_visible_locator(ctx, self.OAUTH_CONTINUE_SELECTORS)
        if locator is not None:
            return locator

        try:
            current_url = ctx.url or ""
        except Exception:
            current_url = ""

        if any(token in current_url for token in ["accounts.snapchat.com", "oauth", "authorize", "consent"]):
            try:
                generic_submit = ctx.locator("button, input[type='submit']")
                actionable_submit = await self.first_actionable_locator(generic_submit)
                if actionable_submit is not None:
                    return actionable_submit
            except Exception:
                pass

        return None

    async def find_female_avatar_locator(self, ctx):
        locator = await self.find_first_visible_locator(ctx, self.FEMALE_AVATAR_SELECTORS)
        if locator is not None:
            return locator

        fallback_selectors = [
            ".gender-select button",
            "button:has(img)",
            "button:has(svg)",
            "[role='button']:has(img)",
            "[role='button']:has(svg)",
        ]

        for selector in fallback_selectors:
            try:
                options = ctx.locator(selector)
                if await options.count() == 2:
                    return options.nth(1)
            except Exception:
                continue

        return None

    async def click_female_avatar_by_layout(self):
        for ctx in await self.get_contexts():
            try:
                clicked = await ctx.evaluate(
                    """() => {
                        const clickElement = (el) => {
                            if (!el) return false;
                            const rect = el.getBoundingClientRect();
                            const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0;
                            if (!visible || el.disabled) return false;

                            el.scrollIntoView({ block: "center", inline: "center" });
                            el.focus?.();
                            el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("pointerup", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
                            return true;
                        };

                        const directFemaleButton = document.querySelector(".gender-select button .gender-icon.female")?.closest("button");
                        if (clickElement(directFemaleButton)) {
                            return true;
                        }

                        const genderButtons = Array.from(document.querySelectorAll(".gender-select button"));
                        if (genderButtons.length >= 2 && clickElement(genderButtons[1])) {
                            return true;
                        }

                        const localizedLabels = ["female", "femenino", "feminino", "feminin", "femme", "donna", "mujer"];
                        const labeledMatch = Array.from(document.querySelectorAll("button, [role='button'], a[role='button'], a"))
                            .find((el) => {
                                const text = `${el.innerText || ""} ${el.getAttribute("aria-label") || ""}`.trim().toLowerCase();
                                return localizedLabels.some((label) => text.includes(label));
                            });
                        if (clickElement(labeledMatch)) {
                            return true;
                        }

                        const centerX = window.innerWidth / 2;
                        const centerY = window.innerHeight / 2;
                        const candidates = Array.from(
                            document.querySelectorAll("button, [role='button'], div[tabindex], a")
                        )
                            .map((el) => {
                                const rect = el.getBoundingClientRect();
                                const hasImage = !!el.querySelector("img, svg, canvas");
                                const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0;
                                if (!hasImage || !visible) {
                                    return null;
                                }

                                const centerDistance = Math.abs((rect.left + (rect.width / 2)) - centerX) + Math.abs((rect.top + (rect.height / 2)) - centerY);
                                const score = rect.width + rect.height - centerDistance;
                                return { el, rect, score };
                            })
                            .filter(Boolean)
                            .sort((a, b) => b.score - a.score || a.rect.left - b.rect.left);

                        if (candidates.length < 2) {
                            return false;
                        }

                        const sideBySide = candidates
                            .filter(({ rect }) => rect.width >= 48 && rect.height >= 48)
                            .sort((a, b) => a.rect.left - b.rect.left);
                        const female = sideBySide.length >= 2 ? sideBySide[sideBySide.length - 1] : candidates[1];
                        return clickElement(female?.el || null);
                    }"""
                )
                if clicked:
                    return True
            except Exception:
                continue
        return False

    async def retry_click_action(
        self,
        locator_getter,
        action_name,
        success_check=None,
        retries=3,
        pre_hover=False,
        think_delay=(1.0, 1.8),
        respect_speed=True,
        respect_jitter=True,
    ):
        last_error = None

        for attempt in range(retries):
            try:
                target = await locator_getter()
                if target is None:
                    if success_check is not None:
                        try:
                            if await success_check():
                                return True
                        except Exception:
                            pass
                    raise Exception(f"{action_name} target not found")

                try:
                    await target.scroll_into_view_if_needed()
                except Exception:
                    pass

                if pre_hover:
                    try:
                        await target.hover(timeout=1500)
                    except Exception:
                        pass

                try:
                    await target.click(timeout=2500)
                except Exception as click_error:
                    last_error = click_error
                    try:
                        await target.click(force=True, timeout=2500)
                    except Exception:
                        element_handle = await target.element_handle()
                        if element_handle is None:
                            raise
                        await target.page.evaluate(
                            """(element) => {
                                element.scrollIntoView({ block: 'center', inline: 'center' });
                                element.focus?.();
                                element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, cancelable: true, view: window }));
                                element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                                element.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, cancelable: true, view: window }));
                                element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                                element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            }""",
                            element_handle,
                        )

                await self.human_delay(
                    think_delay[0],
                    think_delay[1],
                    kind="think",
                    respect_speed=respect_speed,
                    respect_jitter=respect_jitter,
                )

                if success_check is None or await success_check():
                    return True

                last_error = Exception(f"{action_name} click did not register")
            except Exception as exc:
                last_error = exc
                if success_check is not None:
                    try:
                        if await success_check():
                            return True
                    except Exception:
                        pass
                if self.logger:
                    self.logger.warning(f"Retry click ({attempt + 1}) -> {action_name} | {exc}")
                await asyncio.sleep(0.6)

        raise Exception(f"{action_name} failed after retry: {last_error}")

    async def click_oauth_continue_by_dom(self):
        for ctx in await self.get_contexts():
            try:
                clicked = await ctx.evaluate(
                    """() => {
                        const directButton =
                            document.querySelector("button.ThemeComponents_continueButton__C1AvV") ||
                            document.querySelector("button[class*='ThemeComponents_continueButton']");

                        const triggerClick = (el) => {
                            if (!el) return false;
                            const rect = el.getBoundingClientRect();
                            const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0;
                            if (!visible || el.disabled) return false;

                            el.scrollIntoView({ block: "center", inline: "center" });
                            el.focus();
                            el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("pointerup", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
                            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
                            return true;
                        };

                        if (triggerClick(directButton)) {
                            return true;
                        }

                        const candidates = Array.from(
                            document.querySelectorAll("button, input[type='submit'], a[role='button'], [role='button']")
                        );

                        const continueButton = candidates.find((el) => {
                            const text = (el.innerText || el.value || el.textContent || "").trim().toLowerCase();
                            const rect = el.getBoundingClientRect();
                            const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0;
                            return visible && (
                                text === "continue" ||
                                text.includes("continue to bitmoji") ||
                                text.includes("agree") ||
                                text.includes("allow") ||
                                text.includes("accept")
                            );
                        });

                        if (!continueButton) {
                            return false;
                        }

                        return triggerClick(continueButton);
                    }"""
                )
                if clicked:
                    return True
            except Exception:
                continue

        return False

    async def is_login_step_cleared(self):
        for ctx in await self.get_contexts():
            if await self.find_login_with_snapchat_locator(ctx) is not None:
                return False
            if await self.is_snapchat_login_context(ctx):
                return False
        return True

    async def is_login_button_cleared(self):
        for ctx in await self.get_contexts():
            if await self.find_login_with_snapchat_locator(ctx) is not None:
                return False
        return True

    async def is_oauth_continue_cleared(self):
        for ctx in await self.get_contexts():
            if await self.find_oauth_continue_locator(ctx) is not None:
                return False
        return True

    async def is_gender_step_cleared(self):
        try:
            if await self.wait_for_account_home_heading(timeout_ms=250):
                return True
        except Exception:
            pass

        try:
            ctx = await self.get_editor_context()
            if ctx and await self.is_editor_context(ctx):
                return True
        except Exception:
            pass

        for ctx in await self.get_contexts():
            try:
                if await self.find_female_avatar_locator(ctx) is not None:
                    return False
            except Exception:
                continue

        state = await self.check_session_state(fast=True)
        return state in {"EDITOR", "ACCOUNT_HOME"} or state != "GENDER"

    async def wait_for_initial_page_signal(self, timeout_ms=None, detect_proxy_failure=True):
        if timeout_ms is None:
            timeout_ms = self.page_load_timeout_ms

        end_time = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)

        while asyncio.get_event_loop().time() < end_time:
            try:
                if await self.wait_for_account_home_heading(timeout_ms=250):
                    return "ACCOUNT_HOME"

                for ctx in await self.get_contexts():
                    try:
                        if await self.is_editor_context(ctx):
                            return "EDITOR"
                        if await self.find_login_with_snapchat_locator(ctx):
                            return "LOGIN"
                        if await self.is_snapchat_login_context(ctx):
                            return "LOGIN"
                        if await self.find_oauth_continue_locator(ctx):
                            return "CONTINUE"
                        if await self.find_female_avatar_locator(ctx):
                            return "GENDER"
                        if await ctx.locator("canvas, .current_preview, [class*='avatar-builder']").count() > 0:
                            return "EDITOR"

                        current_url = ""
                        try:
                            current_url = (ctx.url or "").strip().lower()
                        except Exception:
                            current_url = ""
                        if current_url:
                            if "accounts.snapchat.com/accounts/oauth2" in current_url:
                                return "CONTINUE"
                            if "accounts.snapchat.com" in current_url:
                                return "LOGIN"
                    except Exception:
                        continue
            except Exception:
                pass

            if detect_proxy_failure:
                signal = await self.get_bitmoji_proxy_failure_signal()
                if signal:
                    raise BitmojiProxyFailureError(
                        f"Bitmoji proxy failure detected while waiting for page signal: {signal}"
                    )

            await asyncio.sleep(0.25)

        try:
            fallback_state = await self.check_session_state(fast=True)
            if fallback_state != "UNKNOWN":
                return fallback_state
        except Exception:
            pass

        if detect_proxy_failure:
            signal = await self.get_bitmoji_proxy_failure_signal()
            if signal:
                raise BitmojiProxyFailureError(
                    f"Bitmoji proxy failure detected while waiting for page signal: {signal}"
                )

        try:
            inferred_state = await self.infer_session_state_from_urls()
            if inferred_state != "UNKNOWN":
                return inferred_state
        except Exception:
            pass

        raise Exception("Page did not become interactive after load.")

    async def infer_session_state_from_urls(self):
        for ctx in await self.get_contexts():
            try:
                current_url = (ctx.url or "").strip().lower()
            except Exception:
                current_url = ""

            if not current_url:
                continue

            if "bitmoji.com/home" in current_url:
                return "ACCOUNT_HOME"
            if "sdk.bitmoji.com/web-builder" in current_url:
                return "EDITOR"
            if "accounts.snapchat.com/accounts/oauth2" in current_url:
                return "CONTINUE"
            if "accounts.snapchat.com" in current_url:
                return "LOGIN"
            if "bitmoji.com/avatar/create" in current_url:
                return "GENDER"

        return "UNKNOWN"

    async def attach_to_existing_editor_page(self):
        candidates = []
        for page in await self.get_candidate_pages():
            try:
                url = page.url or ""
                if "bitmoji.com/avatar/create" in url:
                    candidates.append((3, page, url))
                elif "bitmoji.com/avatar" in url:
                    candidates.append((2, page, url))
                elif "bitmoji.com/home" in url:
                    candidates.append((1, page, url))
            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            _, page, url = candidates[0]
            self.page = page
            print(f"Attached to existing Bitmoji page: {url}")
            return page
        return None

    async def get_editor_context(self):
        best_ctx = None
        best_score = -1

        for ctx in await self.get_contexts():
            score = 0

            try:
                current_url = (ctx.url or "").lower()
            except Exception:
                current_url = ""

            if "bitmoji.com/avatar" in current_url:
                score += 4
            elif "bitmoji.com/home" in current_url:
                score += 1

            try:
                if await self.find_save_button_locator(ctx) is not None:
                    score += 5
            except Exception:
                pass

            try:
                score += min(4, await ctx.locator(".top-category-container, .category-item, [class*='category-item']").count())
            except Exception:
                pass

            try:
                if await ctx.locator("#current-category, [class*='traits-container'], [class*='fashion-traits']").count() > 0:
                    score += 4
            except Exception:
                pass

            try:
                if await ctx.locator("img.current_preview, .current_preview, canvas").count() > 0:
                    score += 3
            except Exception:
                pass

            if score > best_score and score >= 4:
                best_ctx = ctx
                best_score = score

        if best_ctx is not None:
            return best_ctx

        return self.page

    async def open_bitmoji_page(self):
        url = "https://www.bitmoji.com/avatar/create/?require_snapchat"
        print("Opening Bitmoji Editor (forced mode)...")

        await self.close_noise_pages()

        existing_page = await self.attach_to_existing_editor_page()
        if existing_page:
            print(f"Current URL: {existing_page.url}")
            try:
                return await self.wait_for_initial_page_signal(timeout_ms=min(8000, self.page_load_timeout_ms))
            except BitmojiProxyFailureError as exc:
                return await self.wait_for_bitmoji_proxy_recovery(url, initial_signal=str(exc))

        self.page = await self.context.new_page()
        last_error = None

        for attempt in range(3):
            try:
                if attempt == 0:
                    await self.page.goto(url, timeout=self.page_load_timeout_ms, wait_until="domcontentloaded")
                else:
                    if self.page.is_closed():
                        self.page = await self.context.new_page()
                    await self.page.goto(url, timeout=min(self.page_load_timeout_ms, 60000), wait_until="domcontentloaded")
            except Exception as exc:
                last_error = exc
                signal = detect_proxy_failure_signal(error=str(exc))
                if self.logger:
                    self.logger.warning(
                        f"Bitmoji create page goto attempt {attempt + 1}/3 raised, "
                        f"checking resulting state instead: {exc}"
                    )
                if signal:
                    return await self.wait_for_bitmoji_proxy_recovery(url, initial_signal=signal)
                await asyncio.sleep(0.6 + (attempt * 0.5))

            await self.close_noise_pages()
            print("Waiting for page to become interactive...")
            try:
                signal_timeout = self.page_load_timeout_ms if attempt == 0 else min(self.page_load_timeout_ms, 30000)
                initial_state = await self.wait_for_initial_page_signal(timeout_ms=signal_timeout)
                print("Page is interactive.")
                print(f"Current URL: {self.page.url}")
                return initial_state
            except BitmojiProxyFailureError as exc:
                last_error = exc
                return await self.wait_for_bitmoji_proxy_recovery(url, initial_signal=str(exc))
            except Exception as exc:
                last_error = exc
                if self.logger:
                    current_url = "unknown"
                    try:
                        current_url = self.page.url
                    except Exception:
                        pass
                    self.logger.warning(
                        f"Bitmoji page was not interactive after load attempt {attempt + 1}/3 "
                        f"(url={current_url}): {exc}"
                    )
                try:
                    await self.page.reload(timeout=30000, wait_until="domcontentloaded")
                except Exception:
                    pass
                await asyncio.sleep(0.8 + (attempt * 0.6))

        raise Exception(f"Page did not become interactive after load. Last error: {last_error}")

    async def select_gender(self):
        print("Waiting for gender selection...")

        target = None
        end_time = asyncio.get_event_loop().time() + min(12.0, (self.navigation_timeout_ms / 1000.0))

        while asyncio.get_event_loop().time() < end_time:
            for ctx in await self.get_contexts():
                target = await self.find_female_avatar_locator(ctx)
                if target is not None:
                    break
            if target is not None:
                break
            await asyncio.sleep(0.08)

        if target is None:
            if await self.click_female_avatar_by_layout():
                print("Female selected")
                return
            raise Exception("Female avatar option not found on localized start page")

        try:
            async def get_gender_target():
                for ctx in await self.get_contexts():
                    gender_target = await self.find_female_avatar_locator(ctx)
                    if gender_target is not None:
                        return gender_target
                return None

            await self.retry_click_action(
                get_gender_target,
                "select_gender",
                success_check=self.is_gender_step_cleared,
                retries=4,
                pre_hover=True,
                think_delay=(0.05, 0.12),
                respect_speed=False,
                respect_jitter=False,
            )
        except Exception:
            if not await self.click_female_avatar_by_layout():
                raise

        print("Female selected")

    async def click_login_with_snapchat(self):
        print("Clicking 'Log In with Snapchat'...")

        target = None
        end_time = asyncio.get_event_loop().time() + (self.navigation_timeout_ms / 1000.0)

        while asyncio.get_event_loop().time() < end_time:
            for ctx in await self.get_contexts():
                target = await self.find_login_with_snapchat_locator(ctx)
                if target is not None:
                    break
            if target is not None:
                break
            await asyncio.sleep(0.25)

        if target is None:
            raise Exception("Login with Snapchat button not found")

        async def get_login_target():
            for ctx in await self.get_contexts():
                login_target = await self.find_login_with_snapchat_locator(ctx)
                if login_target is not None:
                    return login_target
            return None

        await self.human_delay(1, 2)
        await self.retry_click_action(
            get_login_target,
            "click_login_with_snapchat",
            success_check=self.is_login_button_cleared,
            retries=3,
            think_delay=(2.0, 3.0),
        )

    async def wait_for_manual_login_resume(self, progress_callback=None):
        print("Manual Snapchat login required. Waiting for the profile to leave the login page...")

        end_time = asyncio.get_event_loop().time() + float(self.manual_login_wait_seconds)
        auth_noted = False

        while asyncio.get_event_loop().time() < end_time:
            await self.wait_if_paused()
            state = await self.check_session_state(fast=True)

            if state == "LOGIN":
                await asyncio.sleep(1.0)
                continue

            if state == "CONTINUE" and callable(progress_callback) and not auth_noted:
                progress_callback("authorizing_bitmoji")
                auth_noted = True

            if state in {"CONTINUE", "GENDER", "EDITOR", "ACCOUNT_HOME"}:
                return state

            await asyncio.sleep(0.5)

        raise Exception("Timed out waiting for manual Snapchat login to finish.")

    async def handle_oauth_continue(self):
        print("Checking for OAuth Continue...")

        try:
            btn = None
            for ctx in await self.get_contexts():
                btn = await self.find_oauth_continue_locator(ctx)
                if btn is not None:
                    break

            if btn is not None:
                print("Clicking Continue...")
                await self.human_delay(0.1, 0.25)

                async def get_continue_target():
                    for ctx in await self.get_contexts():
                        continue_target = await self.find_oauth_continue_locator(ctx)
                        if continue_target is not None:
                            return continue_target
                    return None

                try:
                    await self.retry_click_action(
                        get_continue_target,
                        "handle_oauth_continue",
                        success_check=self.is_oauth_continue_cleared,
                        retries=6,
                        pre_hover=True,
                        think_delay=(0.1, 0.25),
                    )
                    return
                except Exception:
                    if await self.click_oauth_continue_by_dom():
                        await self.human_delay(0.08, 0.18)
                        return

            if await self.click_oauth_continue_by_dom():
                await self.human_delay(0.08, 0.18)
        except Exception:
            pass
