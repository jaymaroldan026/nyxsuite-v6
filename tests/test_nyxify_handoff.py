import unittest

import nyxify_runner
from core import adspower_extension_cleanup


class NyxifyHandoffTests(unittest.TestCase):
    def test_signup_handoff_timeout_is_not_classified_as_extension_cleanup(self):
        message = (
            "Snapchat signup handoff timed out after 300s for AdsPower profile k1dadmrp. "
            "last_stage=waiting_for_signup_page; pages=[0:about:blank]"
        )

        self.assertEqual(
            nyxify_runner._classify_failure_last_step(
                {"profile_id": "k1dadmrp"},
                "opening_profile",
                message,
            ),
            "signup_handoff_failed",
        )

    def test_signup_url_detection_accepts_snapchat_signup_variants(self):
        self.assertTrue(
            adspower_extension_cleanup._is_snapchat_signup_url(
                "https://accounts.snapchat.com/v2/signup?foo=bar"
            )
        )
        self.assertFalse(
            adspower_extension_cleanup._is_snapchat_signup_url(
                "https://accounts.snapchat.com/v2/login"
            )
        )


if __name__ == "__main__":
    unittest.main()
