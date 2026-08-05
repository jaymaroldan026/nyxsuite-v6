"""Phone/SMS verification recovery.

When the SMS code never arrives, Nyxify should NOT fail the account (which
deletes the AdsPower profile and recreates it). Instead it goes back to the
phone-entry step, orders a fresh number (force_new — which waits out SnapBoard's
~60s redo cooldown so the number actually changes) and refetches the OTP on the
SAME account. These cover ``_recover_sms_via_new_phone`` and its wiring.
"""
import unittest
from unittest import mock

from core import signup_flow


def _async_page():
    page = mock.Mock()
    page.wait_for_timeout = mock.AsyncMock()
    return page


class RecoverSmsViaNewPhoneTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_code_after_ordering_a_fresh_number(self):
        page = _async_page()
        sms_fetcher = mock.Mock(return_value="654321")
        with mock.patch.object(signup_flow, "_resolve_active_signup_page", mock.AsyncMock(return_value=page)), \
             mock.patch.object(signup_flow, "_click_verification_back_button", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_is_phone_verification_step", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_emit_signup_progress", mock.AsyncMock()), \
             mock.patch.object(signup_flow, "_fetch_phone_from_provider", mock.AsyncMock(return_value="+15551230000")), \
             mock.patch.object(signup_flow, "_fill_and_submit_phone_number", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_wait_for_signup_progress", mock.AsyncMock(return_value="otp")):
            code, out_page = await signup_flow._recover_sms_via_new_phone(
                page, phone_fetcher=mock.Mock(), sms_fetcher=sms_fetcher, logger=None, profile_id="1"
            )
        self.assertEqual(code, "654321")
        self.assertIs(out_page, page)

    async def test_forces_a_new_number(self):
        page = _async_page()
        fetch_phone = mock.AsyncMock(return_value="+15551230000")
        with mock.patch.object(signup_flow, "_resolve_active_signup_page", mock.AsyncMock(return_value=page)), \
             mock.patch.object(signup_flow, "_click_verification_back_button", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_is_phone_verification_step", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_emit_signup_progress", mock.AsyncMock()), \
             mock.patch.object(signup_flow, "_fetch_phone_from_provider", fetch_phone), \
             mock.patch.object(signup_flow, "_fill_and_submit_phone_number", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_wait_for_signup_progress", mock.AsyncMock(return_value="otp")):
            await signup_flow._recover_sms_via_new_phone(
                page, phone_fetcher=mock.Mock(), sms_fetcher=mock.Mock(return_value="1"), logger=None, profile_id="1"
            )
        # The replacement must be ordered with force_new=True (rotates the number).
        self.assertEqual(fetch_phone.await_args.kwargs.get("force_new"), True)

    async def test_no_fetchers_is_a_safe_noop(self):
        page = _async_page()
        code, out_page = await signup_flow._recover_sms_via_new_phone(
            page, phone_fetcher=None, sms_fetcher=None, logger=None, profile_id="1"
        )
        self.assertEqual(code, "")
        self.assertIs(out_page, page)

    async def test_welcome_after_new_number_stops_without_sms(self):
        """A fresh number that completes signup on its own (no code step) must
        not keep hunting for an SMS."""
        page = _async_page()
        sms_fetcher = mock.Mock(return_value="999999")
        with mock.patch.object(signup_flow, "_resolve_active_signup_page", mock.AsyncMock(return_value=page)), \
             mock.patch.object(signup_flow, "_click_verification_back_button", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_is_phone_verification_step", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_emit_signup_progress", mock.AsyncMock()), \
             mock.patch.object(signup_flow, "_fetch_phone_from_provider", mock.AsyncMock(return_value="+15551230000")), \
             mock.patch.object(signup_flow, "_fill_and_submit_phone_number", mock.AsyncMock(return_value=True)), \
             mock.patch.object(signup_flow, "_wait_for_signup_progress", mock.AsyncMock(return_value="welcome")):
            code, _ = await signup_flow._recover_sms_via_new_phone(
                page, phone_fetcher=mock.Mock(), sms_fetcher=sms_fetcher, logger=None, profile_id="1"
            )
        self.assertEqual(code, "")
        sms_fetcher.assert_not_called()

    async def test_gives_up_when_phone_step_never_returns(self):
        page = _async_page()
        with mock.patch.object(signup_flow, "_resolve_active_signup_page", mock.AsyncMock(return_value=page)), \
             mock.patch.object(signup_flow, "_click_verification_back_button", mock.AsyncMock(return_value=False)), \
             mock.patch.object(signup_flow, "_is_phone_verification_step", mock.AsyncMock(return_value=False)):
            code, out_page = await signup_flow._recover_sms_via_new_phone(
                page, phone_fetcher=mock.Mock(), sms_fetcher=mock.Mock(), logger=None, profile_id="1"
            )
        self.assertEqual(code, "")
        self.assertIs(out_page, page)


class FetchPhoneFromProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_passes_force_new_and_awaits_coroutine(self):
        async def fetcher(force_new=False):
            return "+1999" if force_new else "+1000"

        got = await signup_flow._fetch_phone_from_provider(fetcher, force_new=True, profile_id="1")
        self.assertEqual(got, "+1999")

    async def test_tolerates_sync_fetcher_without_force_new(self):
        got = await signup_flow._fetch_phone_from_provider(lambda: "+15550000", force_new=True, profile_id="1")
        self.assertEqual(got, "+15550000")

    async def test_none_fetcher_returns_blank(self):
        self.assertEqual(await signup_flow._fetch_phone_from_provider(None, force_new=True), "")


class SmsRecoveryWiringTests(unittest.TestCase):
    def test_handler_calls_recovery_before_giving_up(self):
        import inspect

        src = inspect.getsource(signup_flow._handle_optional_phone_sms_verification)
        self.assertIn("_recover_sms_via_new_phone(", src)


if __name__ == "__main__":
    unittest.main()
