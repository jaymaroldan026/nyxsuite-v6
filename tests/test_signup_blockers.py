"""Tests for the Nyxify signup-blocker handling added in Phase 1.

Covers:
  * the runner classifier/cleanup wiring for the new blocker error classes
    (reCAPTCHA stall, non-English page, "mobile app" block, email order
    unavailable), and
  * the signup_flow page detectors that raise those errors.
"""

import unittest

import nyxify_runner
from core import signup_flow
from core import nyxify_guard


class ClassifyBlockerErrorsTests(unittest.TestCase):
    """Each blocker error must classify to its own step AND be cleanup-eligible
    so the runner deletes the profile, rotates the proxy, and requeues PENDING.
    """

    CASES = {
        "account_creation_blocked: please try again on our mobile app.": "account_creation_blocked",
        "signup_non_english_page: page rendered in a language the bot cannot drive.": "signup_non_english_page",
        "signup_stuck_retry_exhausted: still stuck after 3 refresh attempts.": "signup_stuck_retry_exhausted",
        "email_order_unavailable: SnapBoard had no verification email.": "email_order_unavailable",
    }

    def test_blocker_errors_classify_to_their_step(self):
        for error_message, expected_step in self.CASES.items():
            with self.subTest(error=error_message):
                step = nyxify_runner._classify_failure_last_step(
                    {"profile_id": "k1abc"},
                    "running_signup",
                    error_message,
                )
                self.assertEqual(step, expected_step)

    def test_blocker_steps_trigger_cleanup_retry(self):
        for expected_step in self.CASES.values():
            with self.subTest(step=expected_step):
                self.assertTrue(
                    nyxify_runner._should_cleanup_failed_created_profile(expected_step, ""),
                    f"{expected_step} should be cleanup-eligible",
                )


class FakePage:
    """Minimal stand-in for a Playwright page for the signup_flow detectors.

    ``evaluate`` distinguishes the two call shapes the detectors use:
      * ``evaluate(js, needle_list)`` — visible-text scan (returns bool)
      * ``evaluate(js)`` — language probe (returns the configured dict) or the
        reCAPTCHA-widget probe (returns the configured bool).
    """

    def __init__(self, text="", lang_info=None, recaptcha=True):
        self._text = str(text or "").lower()
        self._lang_info = dict(lang_info or {})
        self._recaptcha = recaptcha

    async def evaluate(self, js, arg=None):
        if isinstance(arg, list):
            return any(str(needle).lower() in self._text for needle in arg)
        js_text = str(js)
        if "htmlLang" in js_text:
            return dict(self._lang_info)
        if "grecaptcha-badge" in js_text:
            return self._recaptcha
        return False


class SignupDetectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_recaptcha_connect_error_detected(self):
        page = FakePage(
            text="Could not connect to the reCAPTCHA service. Please check your internet connection "
            "and reload to get a reCAPTCHA challenge."
        )
        self.assertTrue(await signup_flow._is_recaptcha_connect_error_visible(page))

    async def test_recaptcha_connect_error_absent(self):
        page = FakePage(text="Sign Up — Step 1 of 3")
        self.assertFalse(await signup_flow._is_recaptcha_connect_error_visible(page))

    async def test_account_creation_blocked_detected(self):
        page = FakePage(
            text="Account creation could not be completed at this time. Please try again on our mobile app."
        )
        self.assertTrue(await signup_flow._is_account_creation_blocked_visible(page))

    async def test_arabic_page_is_non_english(self):
        # Mirrors the Arabic signup screenshot: lang=ar, all non-Latin script.
        page = FakePage(lang_info={"lang": "ar", "nonLatin": 25, "latin": 0})
        self.assertTrue(await signup_flow._is_non_english_signup_page(page))

    async def test_chinese_page_is_non_english(self):
        page = FakePage(lang_info={"lang": "zh-cn", "nonLatin": 18, "latin": 2})
        self.assertTrue(await signup_flow._is_non_english_signup_page(page))

    async def test_english_page_is_not_flagged(self):
        page = FakePage(lang_info={"lang": "en-US", "nonLatin": 0, "latin": 42})
        self.assertFalse(await signup_flow._is_non_english_signup_page(page))

    async def test_english_lang_with_stray_glyphs_not_flagged(self):
        # A mostly-English page with a couple of emoji/accents must NOT churn.
        page = FakePage(lang_info={"lang": "en", "nonLatin": 2, "latin": 40})
        self.assertFalse(await signup_flow._is_non_english_signup_page(page))


class FakeNyxifyStore:
    def __init__(self, task=None, inflight=False):
        self._task = task
        self._inflight = inflight

    def get_task_by_adspower_profile_id(self, profile_id):
        return self._task

    def has_inflight_signups(self):
        return self._inflight


class GuardTests(unittest.TestCase):
    """The intermittent early-run leak was the guard failing OPEN when no Nyxify
    task matched. It must now hold (a) in strict mode, and (b) while Nyxify has
    signups in flight — while still allowing standalone Nyx when idle."""

    def test_no_task_idle_fails_open(self):
        store = FakeNyxifyStore(task=None, inflight=False)
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store)
        self.assertFalse(guard["locked"])

    def test_no_task_with_inflight_signups_holds(self):
        store = FakeNyxifyStore(task=None, inflight=True)
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store)
        self.assertTrue(guard["locked"])

    def test_no_task_strict_holds_even_when_idle(self):
        store = FakeNyxifyStore(task=None, inflight=False)
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store, strict=True)
        self.assertTrue(guard["locked"])

    def test_running_task_holds(self):
        store = FakeNyxifyStore(task={"status": "RUNNING", "last_step": "running_signup"})
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store)
        self.assertTrue(guard["locked"])

    def test_completed_task_releases(self):
        store = FakeNyxifyStore(task={"status": "DONE", "last_step": "signup_complete"})
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store)
        self.assertFalse(guard["locked"])

    def test_done_but_incomplete_holds(self):
        store = FakeNyxifyStore(task={"status": "DONE", "last_step": "awaiting_email_verification"})
        guard = nyxify_guard.get_nyxify_profile_guard("k1abc", store=store)
        self.assertTrue(guard["locked"])


if __name__ == "__main__":
    unittest.main()
