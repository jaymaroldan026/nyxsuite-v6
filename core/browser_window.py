async def maximize_browser_window(browser, logger=None):
    contexts = list(getattr(browser, "contexts", []) or [])
    for context in contexts:
        pages = list(getattr(context, "pages", []) or [])
        for page in pages:
            try:
                await page.bring_to_front()
            except Exception:
                pass

            try:
                session = await context.new_cdp_session(page)
                details = await session.send("Browser.getWindowForTarget")
                window_id = details.get("windowId")
                if window_id:
                    await session.send(
                        "Browser.setWindowBounds",
                        {
                            "windowId": window_id,
                            "bounds": {"windowState": "maximized"},
                        },
                    )
                    return True
            except Exception as exc:
                if logger:
                    logger.debug(f"Could not maximize browser window via CDP: {exc}")
                continue
    return False
