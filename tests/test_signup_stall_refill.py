"""Tests for the Nyxify signup stall-recovery additions:

  * ``_signup_form_is_blank`` / ``_submit_is_clickable`` predicates, and
  * ``_wait_for_signup_progress``:
      - re-enters the saved credentials when the form is detected blank
        (e.g. after a manual page refresh), and
      - hard-refreshes when stuck on the page for a very long time and
        "Agree and Continue" never becomes clickable (even with a captcha),
      - refreshes when neither the signup form nor a verification handoff is
        detected for the stall window.
"""
import time
import unittest
from unittest import mock

from core import signup_flow


def _only_form(_page, selectors):
    # on_form probe includes '#firstname'; the submit probe does not. Returning
    # '' for the submit probe keeps the enabled/disabled branch out of the way.
    return "#firstname" if "#firstname" in selectors else ""


class SignupPredicateTests(unittest.IsolatedAsyncioTestCase):
    async def test_form_is_blank_when_key_fields_empty(self):
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="#firstname")), \
             mock.patch.object(signup_flow, "_read_input_value", mock.AsyncMock(side_effect=["", ""])):
            self.assertTrue(await signup_flow._signup_form_is_blank(object()))

    async def test_form_not_blank_when_firstname_filled(self):
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="#firstname")), \
             mock.patch.object(signup_flow, "_read_input_value", mock.AsyncMock(side_effect=["Clea", ""])):
            self.assertFalse(await signup_flow._signup_form_is_blank(object()))

    async def test_form_not_blank_when_not_on_signup_step(self):
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="")):
            self.assertFalse(await signup_flow._signup_form_is_blank(object()))

    async def test_submit_clickable_when_enabled(self):
        page = mock.Mock()
        page.evaluate = mock.AsyncMock(return_value=False)  # not disabled
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="button[type='submit']")):
            self.assertTrue(await signup_flow._submit_is_clickable(page, ["button[type='submit']"]))

    async def test_submit_not_clickable_when_disabled(self):
        page = mock.Mock()
        page.evaluate = mock.AsyncMock(return_value=True)  # disabled
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="button[type='submit']")):
            self.assertFalse(await signup_flow._submit_is_clickable(page, ["button[type='submit']"]))

    async def test_submit_not_clickable_when_absent(self):
        with mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value="")):
            self.assertFalse(await signup_flow._submit_is_clickable(mock.Mock(), ["button[type='submit']"]))


class FakeProgressPage:
    url = "https://accounts.snapchat.com/v2/signup"

    def __init__(self):
        self.waits = []

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)


class SignupInitialSubmitRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_submit_failure_refreshes_and_refills_signup_form(self):
        page = FakeProgressPage()
        steps = []
        fill_form = mock.AsyncMock(return_value={"submitted": False, "username": "clearetry"})
        reload_refill = mock.AsyncMock(return_value=True)
        handle_verification = mock.AsyncMock(
            return_value={
                "reached_verification": True,
                "otp_entered": True,
                "final_username": "clearetry",
                "email": "clea@example.com",
            }
        )

        with mock.patch.object(signup_flow, "_keep_signup_page_clear", mock.AsyncMock(return_value=False)), \
             mock.patch.object(signup_flow, "_wait_visible", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_is_non_english_signup_page", mock.AsyncMock(return_value=False)), \
             mock.patch.object(signup_flow, "get_random_name", return_value="Clea"), \
             mock.patch.object(signup_flow, "generate_birthday", return_value={"month": 7, "day": 6, "year": "2004"}), \
             mock.patch.object(signup_flow, "_fill_signup_form", fill_form), \
             mock.patch.object(signup_flow, "_reload_and_refill_signup", reload_refill), \
             mock.patch.object(signup_flow, "_handle_verification", handle_verification):
            result = await signup_flow.perform_snapchat_signup(
                page,
                model="Clea",
                username="clearetry",
                email="clea@example.com",
                names_dir=".",
                logger=None,
                profile_id="k1retry",
                otp_fetcher=mock.AsyncMock(return_value="123456"),
                progress_callback=lambda step: steps.append(step),
            )

        self.assertEqual(result["error"], "")
        reload_refill.assert_awaited_once_with(
            page,
            "Clea",
            {"month": 7, "day": 6, "year": "2004"},
            "clearetry",
            "",
            None,
            "k1retry",
        )
        handle_verification.assert_awaited_once()
        self.assertIn("refreshing_stuck_signup", steps)


class SignupStallRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_default_refresh_windows_are_100_and_200_seconds(self):
        self.assertEqual(signup_flow.SIGNUP_STALL_SECONDS, 100)
        self.assertEqual(signup_flow.SIGNUP_HARD_STALL_SECONDS, 200)

    def _common_patches(self):
        # Neutralize every branch that precedes the A2 stall block so the loop
        # falls straight through to it.
        return [
            mock.patch.object(signup_flow, "_resolve_active_signup_page", mock.AsyncMock(side_effect=lambda p, *_a, **_k: p)),
            mock.patch.object(signup_flow, "_is_account_creation_blocked_visible", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_is_recaptcha_connect_error_visible", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_read_input_value", mock.AsyncMock(return_value="")),
            mock.patch.object(signup_flow, "_is_username_taken_error_visible", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_detect_signup_handoff_stage", mock.AsyncMock(return_value="")),
            mock.patch.object(signup_flow, "_is_unable_to_process_error_visible", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(side_effect=_only_form)),
        ]

    async def test_blank_form_triggers_refill_from_credentials(self):
        page = FakeProgressPage()
        refill = mock.AsyncMock(return_value=True)
        resubmit = mock.AsyncMock(return_value=True)
        stall_state = {"refresh_attempts": 0, "form_since": None,
                       "blank_refill_attempts": 0, "refill": refill}
        steps = []

        patches = self._common_patches() + [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=True)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            progress_callback=lambda s: steps.append(s),
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        refill.assert_awaited_once()
        resubmit.assert_not_awaited()          # blank re-fill must NOT reload
        self.assertIn("refilling_signup_form", steps)
        self.assertEqual(stall_state["blank_refill_attempts"], 1)

    async def test_hard_stall_refreshes_when_submit_never_clickable_with_captcha(self):
        page = FakeProgressPage()
        refill = mock.AsyncMock(return_value=True)
        resubmit = mock.AsyncMock(return_value=True)
        # Pretend we've been sitting on the form well past the hard-stall window.
        old = time.monotonic() - (signup_flow.SIGNUP_HARD_STALL_SECONDS + 30)
        stall_state = {"refresh_attempts": 0, "form_since": old,
                       "blank_refill_attempts": 0, "refill": refill}
        steps = []

        patches = self._common_patches() + [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=True)),
            mock.patch.object(signup_flow, "_submit_is_clickable", mock.AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            progress_callback=lambda s: steps.append(s),
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        resubmit.assert_awaited_once()
        refill.assert_not_awaited()
        self.assertIn("refreshing_stuck_signup", steps)
        self.assertEqual(stall_state["refresh_attempts"], 1)

    async def test_filled_signup_form_refreshes_when_captcha_icon_never_appears(self):
        page = FakeProgressPage()
        refill = mock.AsyncMock(return_value=True)
        resubmit = mock.AsyncMock(return_value=True)
        old = time.monotonic() - (signup_flow.SIGNUP_STALL_SECONDS + 5)
        stall_state = {"refresh_attempts": 0, "form_since": old,
                       "blank_refill_attempts": 0, "refill": refill}
        steps = []

        patches = self._common_patches() + [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_submit_is_clickable", mock.AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            progress_callback=lambda s: steps.append(s),
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        resubmit.assert_awaited_once()
        refill.assert_not_awaited()
        self.assertIn("refreshing_stalled_signup", steps)
        self.assertEqual(stall_state["refresh_attempts"], 1)

    async def test_no_hard_refresh_while_submit_is_clickable(self):
        # Long time on the form but the button IS clickable -> do NOT hard-refresh
        # (we're waiting on a legitimate handoff, not stuck).
        page = FakeProgressPage()
        resubmit = mock.AsyncMock(return_value=True)
        old = time.monotonic() - (signup_flow.SIGNUP_HARD_STALL_SECONDS + 30)
        stall_state = {"refresh_attempts": 0, "form_since": old,
                       "blank_refill_attempts": 0, "refill": mock.AsyncMock()}

        patches = self._common_patches() + [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=True)),
            mock.patch.object(signup_flow, "_submit_is_clickable", mock.AsyncMock(return_value=True)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        resubmit.assert_not_awaited()

    async def test_unexpected_page_refreshes_when_signup_form_missing(self):
        page = FakeProgressPage()
        resubmit = mock.AsyncMock(return_value=True)
        old = time.monotonic() - (signup_flow.SIGNUP_STALL_SECONDS + 5)
        stall_state = {"refresh_attempts": 0, "form_since": None,
                       "blank_refill_attempts": 0, "page_issue_since": old,
                       "refill": mock.AsyncMock()}
        steps = []

        patches = self._common_patches()
        patches[-1] = mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value=""))
        patches += [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=True)),
            mock.patch.object(signup_flow, "_submit_is_clickable", mock.AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            progress_callback=lambda s: steps.append(s),
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        resubmit.assert_awaited_once()
        self.assertIn("refreshing_signup_page_issue", steps)
        self.assertEqual(stall_state["refresh_attempts"], 1)

    async def test_unexpected_page_waits_until_stall_window_expires(self):
        page = FakeProgressPage()
        resubmit = mock.AsyncMock(return_value=True)
        old = time.monotonic() - max(1, signup_flow.SIGNUP_STALL_SECONDS - 10)
        stall_state = {"refresh_attempts": 0, "form_since": None,
                       "blank_refill_attempts": 0, "page_issue_since": old,
                       "refill": mock.AsyncMock()}

        patches = self._common_patches()
        patches[-1] = mock.patch.object(signup_flow, "_visible_any", mock.AsyncMock(return_value=""))
        patches += [
            mock.patch.object(signup_flow, "_signup_form_is_blank", mock.AsyncMock(return_value=False)),
            mock.patch.object(signup_flow, "_recaptcha_widget_present", mock.AsyncMock(return_value=True)),
            mock.patch.object(signup_flow, "_submit_is_clickable", mock.AsyncMock(return_value=False)),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

        stage = await signup_flow._wait_for_signup_progress(
            page, logger=None, profile_id="777", timeout_ms=1000,
            resubmit_callback=resubmit, stall_state=stall_state,
        )

        self.assertEqual(stage, "")
        resubmit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
