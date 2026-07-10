"""Tests for Nyxify's proxy blocker matching (nyxify_runner._is_proxy_banned)."""

import unittest

import nyxify_runner


class IsProxyBannedTests(unittest.TestCase):
    def test_subnet_prefix_match(self):
        self.assertTrue(nyxify_runner._is_proxy_banned("130.24.5.7:8080", ["130.24"]))

    def test_first_octet_prefix_blocks_whole_range(self):
        self.assertTrue(nyxify_runner._is_proxy_banned("130.99.1.1:9000", ["130"]))

    def test_full_proxy_string_match(self):
        self.assertTrue(
            nyxify_runner._is_proxy_banned("109.176.200.39:57813", ["109.176.200.39:57813"])
        )

    def test_substring_match(self):
        self.assertTrue(nyxify_runner._is_proxy_banned("user@82.26.10.5:3128", ["82.26"]))

    def test_no_match(self):
        self.assertFalse(nyxify_runner._is_proxy_banned("45.10.1.1:80", ["130", "82.26"]))

    def test_empty_proxy_never_banned(self):
        self.assertFalse(nyxify_runner._is_proxy_banned("", ["130"]))

    def test_empty_banlist_never_bans(self):
        self.assertFalse(nyxify_runner._is_proxy_banned("130.24.5.7:8080", []))

    def test_blank_ban_patterns_ignored(self):
        self.assertFalse(nyxify_runner._is_proxy_banned("130.24.5.7:8080", ["", "   "]))

    def test_case_insensitive_hostname(self):
        self.assertTrue(
            nyxify_runner._is_proxy_banned("Proxy.Example.COM:9000", ["proxy.example.com"])
        )


if __name__ == "__main__":
    unittest.main()
