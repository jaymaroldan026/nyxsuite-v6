"""Tests for the per-subnet Proxy Ranking store (core/proxy_ranking_store.py)."""

import os
import tempfile
import unittest

from core.proxy_ranking_store import ProxyRankingStore, compute_score, subnet_of


class SubnetOfTests(unittest.TestCase):
    def test_ipv4_host_port(self):
        self.assertEqual(subnet_of("130.24.5.7:8080"), "130.24")

    def test_ipv4_with_credentials(self):
        self.assertEqual(subnet_of("user:pass@130.24.5.7:8080"), "130.24")

    def test_ipv4_bare(self):
        self.assertEqual(subnet_of("45.10.1.1"), "45.10")

    def test_custom_octets(self):
        self.assertEqual(subnet_of("130.24.5.7:8080", octets=3), "130.24.5")

    def test_hostname_proxy_falls_back_to_host(self):
        self.assertEqual(subnet_of("proxy.example.com:9000"), "proxy.example.com")

    def test_empty(self):
        self.assertEqual(subnet_of(""), "")
        self.assertEqual(subnet_of(None), "")


class ComputeScoreTests(unittest.TestCase):
    def test_clean_subnet_scores_zero(self):
        self.assertEqual(compute_score(uses=5, retries=0, creation_fails=0, ban_hits=0), 0.0)

    def test_weights_ban_highest(self):
        # (1*1 + 2*0 + 3*1) / 2 uses = 2.0
        self.assertEqual(compute_score(uses=2, retries=1, creation_fails=0, ban_hits=1), 2.0)

    def test_normalized_by_uses(self):
        few = compute_score(uses=1, retries=2, creation_fails=0, ban_hits=0)
        many = compute_score(uses=10, retries=2, creation_fails=0, ban_hits=0)
        self.assertGreater(few, many)

    def test_zero_uses_does_not_divide_by_zero(self):
        # uses is floored to 1 internally.
        self.assertEqual(compute_score(uses=0, retries=1, creation_fails=0, ban_hits=0), 1.0)


class ProxyRankingStoreTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.store = ProxyRankingStore(db_path=os.path.join(self._dir, "pr.db"))

    def test_records_group_by_subnet_and_rank_good_to_bad(self):
        self.store.record_use("130.24.5.7:8080")
        self.store.record_use("130.24.9.9:1000")  # same subnet, different host/port
        self.store.record_retry("130.24.5.7:8080", reason="blocked")
        self.store.record_ban_hit("130.24.5.7:8080")
        self.store.record_use("45.10.1.1:80")  # clean subnet

        ranked = self.store.ranked()
        subnets = [r["subnet"] for r in ranked]
        self.assertEqual(subnets[0], "45.10", "clean subnet should rank best (good first)")
        self.assertEqual(subnets[-1], "130.24", "bad subnet should rank worst")

        bad = next(r for r in ranked if r["subnet"] == "130.24")
        self.assertEqual(bad["uses"], 2)
        self.assertEqual(bad["retries"], 1)
        self.assertEqual(bad["ban_hits"], 1)
        self.assertEqual(bad["score"], 2.0)

    def test_unknown_column_rejected(self):
        with self.assertRaises(ValueError):
            self.store._bump("130.24.5.7", "not_a_column")

    def test_blank_proxy_is_ignored(self):
        self.store.record_use("")
        self.assertEqual(self.store.ranked(), [])


if __name__ == "__main__":
    unittest.main()
