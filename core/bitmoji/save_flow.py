import asyncio


class BitmojiSaveMixin:
    async def wait_for_save_submit_clear(self, timeout_seconds=4.0):
        end_time = asyncio.get_event_loop().time() + float(timeout_seconds)

        while asyncio.get_event_loop().time() < end_time:
            if await self.is_save_submit_cleared():
                return True
            await asyncio.sleep(0.2)

        return False

    async def get_save_confirm_target(self):
        for ctx in await self.get_contexts():
            try:
                confirm_target = await self.find_save_confirm_locator(ctx)
                if confirm_target is not None:
                    return confirm_target
            except Exception:
                continue

        return await self.open_save_confirmation()

    async def find_save_button_locator(self, ctx):
        locator = await self.find_first_visible_locator(ctx, self.SAVE_BUTTON_SELECTORS)
        if locator is not None:
            return locator

        try:
            generic_save = ctx.locator("div.save-button button, div[class*='save-button'] button").first
            if await generic_save.count() > 0:
                return generic_save
        except Exception:
            pass

        return None

    async def find_save_confirm_locator(self, ctx):
        locator = await self.find_first_visible_locator(ctx, self.SAVE_CONFIRM_SELECTORS)
        if locator is not None:
            return locator

        try:
            for selector in [
                "[role='dialog'] button:has-text('Save')",
                ".modal button:has-text('Save')",
                "button:has-text('Save')",
                "[role='dialog'] [role='button']:has-text('Save')",
                ".modal [role='button']:has-text('Save')",
            ]:
                candidate = ctx.locator(selector).first
                if await candidate.count() > 0:
                    return candidate
        except Exception:
            pass

        try:
            dialog_buttons = ctx.locator("[role='dialog'] button, .modal button")
            if await dialog_buttons.count() > 0:
                for index in range(await dialog_buttons.count()):
                    candidate = dialog_buttons.nth(index)
                    try:
                        text = (await candidate.inner_text(timeout=250)).strip().lower()
                    except Exception:
                        text = ""
                    if "save" in text or "continue" in text:
                        return candidate
                return dialog_buttons.last
        except Exception:
            pass

        return None

    async def find_save_error_locator(self, ctx):
        return await self.find_first_visible_locator(ctx, self.SAVE_ERROR_SELECTORS)

    async def find_save_cancel_locator(self, ctx):
        return await self.find_first_visible_locator(ctx, self.SAVE_CANCEL_SELECTORS)

    async def is_save_confirmation_visible(self):
        for ctx in await self.get_contexts():
            if await self.find_save_confirm_locator(ctx) is not None:
                return True
        return False

    async def is_save_submit_cleared(self):
        if await self.detect_save_error():
            return True

        for ctx in await self.get_contexts():
            try:
                if await self.find_save_confirm_locator(ctx) is not None:
                    return False
            except Exception:
                continue

        try:
            if await self.wait_for_account_home_heading(timeout_ms=250):
                return True
        except Exception:
            pass

        return True

    async def open_save_confirmation(self):
        if await self.wait_for_account_home_heading(timeout_ms=250):
            return None

        async def get_save_target():
            for ctx in await self.get_contexts():
                save_target = await self.find_save_button_locator(ctx)
                if save_target is not None:
                    return save_target
            return None

        await self.retry_click_action(
            get_save_target,
            "open_save_confirmation",
            success_check=self.is_save_confirmation_visible,
            retries=3,
            think_delay=(0.05, 0.12),
            respect_speed=False,
            respect_jitter=False,
        )

        confirm_target = None
        end_time = asyncio.get_event_loop().time() + (self.navigation_timeout_ms / 1000.0)

        while asyncio.get_event_loop().time() < end_time:
            for ctx in await self.get_contexts():
                confirm_target = await self.find_save_confirm_locator(ctx)
                if confirm_target is not None:
                    break

            if confirm_target is not None:
                return confirm_target

            await asyncio.sleep(0.08)

        raise Exception("Save confirmation button not found")

    async def detect_save_error(self):
        for ctx in await self.get_contexts():
            try:
                error_locator = await self.find_save_error_locator(ctx)
                if error_locator is not None:
                    return True
            except Exception:
                continue
        return False

    async def cancel_save_dialog(self):
        async def get_cancel_target():
            for ctx in await self.get_contexts():
                cancel_target = await self.find_save_cancel_locator(ctx)
                if cancel_target is not None:
                    return cancel_target
            return None

        cancel_target = await get_cancel_target()
        if cancel_target is None:
            return False

        try:
            await self.retry_click_action(
                get_cancel_target,
                "cancel_save_dialog",
                success_check=self.is_save_submit_cleared,
                retries=2,
                think_delay=(0.05, 0.12),
                respect_speed=False,
                respect_jitter=False,
            )
        except Exception:
            try:
                await cancel_target.click()
            except Exception:
                await cancel_target.click(force=True)
            await self.human_delay(0.05, 0.12, kind="think")

        return True

    async def wait_for_save_completion(self, timeout_seconds=None):
        if timeout_seconds is None:
            timeout_seconds = self.long_wait_seconds

        end_time = asyncio.get_event_loop().time() + float(timeout_seconds)

        while asyncio.get_event_loop().time() < end_time:
            await self.wait_if_paused()

            try:
                if await self.wait_for_account_home_heading(timeout_ms=200):
                    self.last_result = "saved_bitmoji"
                    print("Bitmoji save confirmed")
                    return True
            except Exception:
                pass

            for ctx in await self.get_contexts():
                try:
                    if await self.is_account_home_context(ctx):
                        self.last_result = "saved_bitmoji"
                        print("Bitmoji save confirmed")
                        return True
                except Exception:
                    continue

            await asyncio.sleep(0.25)

        if await self.recover_save_completion_state():
            return True

        raise Exception("Bitmoji save confirmation not detected")

    async def recover_save_completion_state(self):
        """Best-effort confirmation for slow Bitmoji saves.

        The editor sometimes accepts the save, redirects slowly, or leaves the
        page in a partial load state. Before marking the profile failed, probe
        all attached pages and then ask Bitmoji home to confirm the account has
        an avatar.
        """
        if self.logger:
            self.logger.warning("Bitmoji save confirmation timed out; probing account home before failing.")

        try:
            if await self.wait_for_account_home_heading(timeout_ms=1500):
                self.last_result = "saved_bitmoji"
                print("Bitmoji save confirmed after timeout")
                return True
        except Exception:
            pass

        for ctx in await self.get_contexts():
            try:
                current_url = (ctx.url or "").strip().lower()
            except Exception:
                current_url = ""

            try:
                if "bitmoji.com/home" in current_url:
                    self.last_result = "saved_bitmoji"
                    print("Bitmoji save confirmed by home URL")
                    return True
                if await self.is_account_home_context(ctx):
                    self.last_result = "saved_bitmoji"
                    print("Bitmoji save confirmed by account context")
                    return True
            except Exception:
                continue

        target_page = self.page
        if target_page is None or target_page.is_closed():
            for page in await self.get_candidate_pages():
                target_page = page
                break

        if target_page is None or target_page.is_closed():
            return False

        try:
            await target_page.goto(
                "https://www.bitmoji.com/home/",
                timeout=min(self.page_load_timeout_ms, 45000),
                wait_until="domcontentloaded",
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"Bitmoji home probe navigation raised: {exc}")

        try:
            if await self.wait_for_account_home_heading(timeout_ms=10000):
                self.last_result = "saved_bitmoji"
                print("Bitmoji save confirmed by home probe")
                return True
        except Exception:
            pass

        return False

    async def save_bitmoji(self):
        await self.wait_if_paused()

        print("Saving Bitmoji...")
        await self.open_save_confirmation()
        print("Confirming Bitmoji save...")
        try:
            await self.retry_click_action(
                self.get_save_confirm_target,
                "submit_save_confirmation",
                success_check=self.wait_for_save_submit_clear,
                retries=2,
                think_delay=(0.05, 0.12),
                respect_speed=False,
                respect_jitter=False,
            )
        except Exception:
            if await self.wait_for_account_home_heading(timeout_ms=400):
                self.last_result = "saved_bitmoji"
                print("Bitmoji save confirmed")
                return True
            await self.open_save_confirmation()
            await self.retry_click_action(
                self.get_save_confirm_target,
                "submit_save_confirmation_reopen",
                success_check=self.wait_for_save_submit_clear,
                retries=2,
                think_delay=(0.05, 0.12),
                respect_speed=False,
                respect_jitter=False,
            )

        if await self.detect_save_error():
            print("Save error detected. Cancelling modal and reopening save...")
            cancelled = await self.cancel_save_dialog()
            if not cancelled:
                raise Exception("Error saving Bitmoji and could not cancel save dialog")

            print("Retrying Bitmoji save from editor...")
            await self.retry_click_action(
                self.get_save_confirm_target,
                "retry_save_confirmation",
                success_check=self.wait_for_save_submit_clear,
                retries=2,
                think_delay=(0.05, 0.12),
                respect_speed=False,
                respect_jitter=False,
            )

            if await self.detect_save_error():
                print("Save error detected again. Trying submit once more...")
                await self.retry_click_action(
                    self.get_save_confirm_target,
                    "final_retry_save_confirmation",
                    success_check=self.wait_for_save_submit_clear,
                    retries=2,
                    think_delay=(0.05, 0.12),
                    respect_speed=False,
                    respect_jitter=False,
                )

                if await self.detect_save_error():
                    raise Exception("Error saving Bitmoji after retry")

        print("Waiting for saved Bitmoji confirmation...")
        return await self.wait_for_save_completion()
