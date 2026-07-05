import unittest

import main
from core.bitmoji.proxy_failure import (
    detect_proxy_failure_signal,
    is_proxy_navigation_error,
    select_proxy_failure_recovery,
)


class NyxProxyFailureTests(unittest.TestCase):
    def test_proxy_navigation_error_maps_to_proxy_error(self):
        message = (
            "Page.goto: net::ERR_PROXY_CONNECTION_FAILED at "
            "https://www.bitmoji.com/avatar/create/?require_snapchat"
        )

        self.assertEqual(main.classify_task_failure(message), "proxy_error")

    def test_adspower_proxy_failure_maps_to_proxy_error(self):
        message = "AdsPower Proxy failure: please check if your network meets the proxy service provider conditions."

        self.assertEqual(main.classify_task_failure(message), "proxy_error")

    def test_existing_bitmoji_failure_still_maps_to_bitmoji_failed(self):
        message = "Page did not become interactive after load."

        self.assertEqual(main.classify_task_failure(message), "bitmoji_failed")

    def test_detector_accepts_chrome_no_internet_proxy_page(self):
        text = (
            "No internet\n"
            "There is something wrong with the proxy server, or the address is incorrect.\n"
            "ERR_PROXY_CONNECTION_FAILED"
        )

        self.assertTrue(
            detect_proxy_failure_signal(
                url="https://www.bitmoji.com/avatar/create/?require_snapchat",
                text=text,
            )
        )

    def test_detector_accepts_adspower_proxy_failure_page(self):
        self.assertEqual(
            detect_proxy_failure_signal(
                url="http://start.adspower.net/?id=k1d95ex5&host=127.0.0.1:20725",
                text="Proxy failure",
            ),
            "AdsPower proxy failure page",
        )

    def test_navigation_error_helper_rejects_generic_timeout(self):
        self.assertFalse(is_proxy_navigation_error("Timeout 30000ms exceeded waiting for selector"))

    def test_proxy_failure_uses_short_timeout_when_host_is_online(self):
        recovery = select_proxy_failure_recovery(probe_func=lambda: True)

        self.assertEqual(recovery["timeout_seconds"], 100)
        self.assertEqual(recovery["failure_kind"], "profile_proxy_failure")
        self.assertTrue(recovery["host_online"])

    def test_proxy_failure_uses_long_timeout_when_host_is_offline(self):
        recovery = select_proxy_failure_recovery(probe_func=lambda: False)

        self.assertEqual(recovery["timeout_seconds"], 300)
        self.assertEqual(recovery["failure_kind"], "host_offline_or_no_internet")
        self.assertFalse(recovery["host_online"])


if __name__ == "__main__":
    unittest.main()
