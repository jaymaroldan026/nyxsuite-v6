"""Regression test for the proxy-recovery livelock.

A profile stuck on the AdsPower "proxy failure" page made
wait_for_initial_page_signal() fall through to check_session_state() and return
"PROXY" — the failure state itself. wait_for_bitmoji_proxy_recovery() treated any
truthy state as "recovered", returned immediately, and wait_for_editor() then
reset its deadline, so the run looped forever (proxy detected -> false recovery
-> repeat) and never freed its concurrency slot. The fix: only a real page state
counts as recovery; a persistent "PROXY" must time out into a proxy_error.
"""

import asyncio
import unittest
from unittest import mock

from core.bitmoji import interaction_flow
from core.bitmoji.interaction_flow import BitmojiInteractionMixin
from core.bitmoji.proxy_failure import BitmojiProxyFailureError


class _FakePage:
    def is_closed(self):
        return False

    async def goto(self, *args, **kwargs):
        return None


class _FakeContext:
    async def new_page(self):
        return _FakePage()


def _make_flow(initial_signal_state):
    flow = BitmojiInteractionMixin.__new__(BitmojiInteractionMixin)
    flow.logger = None
    flow.page = _FakePage()
    flow.context = _FakeContext()

    async def _noop():
        return None

    async def _signal(*args, **kwargs):
        return "AdsPower proxy failure page"

    async def _initial_signal(*args, **kwargs):
        return initial_signal_state

    flow.wait_if_paused = _noop
    flow.get_bitmoji_proxy_failure_signal = _signal
    flow.wait_for_initial_page_signal = _initial_signal
    return flow


# Short, host-online recovery window so the test finishes fast.
_FAST_RECOVERY = {
    "failure_kind": "profile_proxy_failure",
    "host_online": True,
    "timeout_seconds": 1,
}


class ProxyRecoveryLivelockTests(unittest.TestCase):
    def test_persistent_proxy_state_times_out_instead_of_livelocking(self):
        flow = _make_flow("PROXY")
        with mock.patch.object(interaction_flow, "select_proxy_failure_recovery",
                               return_value=_FAST_RECOVERY):
            with self.assertRaises(BitmojiProxyFailureError):
                asyncio.run(flow.wait_for_bitmoji_proxy_recovery("http://x"))

    def test_unknown_state_also_does_not_count_as_recovery(self):
        flow = _make_flow("UNKNOWN")
        with mock.patch.object(interaction_flow, "select_proxy_failure_recovery",
                               return_value=_FAST_RECOVERY):
            with self.assertRaises(BitmojiProxyFailureError):
                asyncio.run(flow.wait_for_bitmoji_proxy_recovery("http://x"))

    def test_real_page_state_is_treated_as_recovery(self):
        flow = _make_flow("EDITOR")
        with mock.patch.object(interaction_flow, "select_proxy_failure_recovery",
                               return_value=_FAST_RECOVERY):
            result = asyncio.run(flow.wait_for_bitmoji_proxy_recovery("http://x"))
        self.assertEqual(result, "EDITOR")


if __name__ == "__main__":
    unittest.main()
