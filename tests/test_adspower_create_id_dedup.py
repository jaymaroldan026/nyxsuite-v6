"""Parallel Nyxify creates must never resolve to the same AdsPower profile id.

The GUI create discovers the new profile's id by scanning the Profiles list. A
transient a11y mis-read of the serial watermark used to make it return the
newest row in the view — which could be another concurrent create's profile —
so two tasks "merged" onto one profile and one AdsPower id landed in two
SnapBoard rows. Discovery now prefers an id that was NOT present before the
create and excludes ids already assigned to another create.
"""

import unittest

# adspower_ui imports fine without pywinauto (the import is guarded); do NOT
# stub pywinauto here — doing so would flip the module's _PYWINAUTO flag for the
# whole test session and make other suites' skip-guards run and fail.
from core import adspower_ui


def _rows(*triples):
    # (serial:int, profile_id:str, name:str)
    return list(triples)


class CreateIdDedupTests(unittest.TestCase):
    def setUp(self):
        # Isolate the process-wide assigned-id registry per test.
        with adspower_ui._ASSIGNED_IDS_LOCK:
            adspower_ui._ASSIGNED_PROFILE_IDS.clear()
        # A controller instance without running __init__ (we only exercise the
        # pure id-picking logic, which uses module-level helpers).
        self.ctrl = adspower_ui.AdsPowerUIController.__new__(adspower_ui.AdsPowerUIController)

    def test_prefers_id_not_present_before_create(self):
        before_ids = {"k1aaaaaa", "k1bbbbbb"}
        rows = _rows(
            (100, "k1aaaaaa", "Snapchat:"),
            (101, "k1bbbbbb", "Snapchat:"),
            (102, "k1cccccc", "Snapchat:"),  # the genuinely new one
        )
        self.assertEqual(self.ctrl._pick_created_id(rows, before_max=101, before_ids=before_ids), "k1cccccc")

    def test_excludes_ids_already_assigned_to_another_create(self):
        # Task A already resolved k1cccccc. Task B scans the same view (glitchy
        # watermark) — it must NOT also pick k1cccccc.
        adspower_ui._remember_assigned_id("k1cccccc")
        rows = _rows(
            (100, "k1aaaaaa", "Snapchat:"),
            (102, "k1cccccc", "Snapchat:"),   # A's, must be skipped
            (103, "k1dddddd", "Snapchat:"),   # B's new one
        )
        before_ids = {"k1aaaaaa", "k1cccccc"}
        self.assertEqual(self.ctrl._pick_created_id(rows, before_max=0, before_ids=before_ids), "k1dddddd")

    def test_stale_zero_watermark_does_not_return_existing_id(self):
        # Watermark mis-read as 0, and the only rows are ones present before the
        # create (all already assigned): discovery must return "" (keep polling)
        # rather than hand back an existing/other id.
        adspower_ui._remember_assigned_id("k1aaaaaa")
        adspower_ui._remember_assigned_id("k1bbbbbb")
        rows = _rows(
            (100, "k1aaaaaa", "Snapchat:"),
            (101, "k1bbbbbb", "Snapchat:"),
        )
        before_ids = {"k1aaaaaa", "k1bbbbbb"}
        self.assertEqual(self.ctrl._pick_created_id(rows, before_max=0, before_ids=before_ids), "")

    def test_falls_back_to_above_watermark_when_before_ids_missing(self):
        # No before-set (legacy path). The above-watermark row is the new one.
        rows = _rows(
            (100, "k1aaaaaa", "Snapchat:"),
            (105, "k1eeeeee", "Snapchat:"),
        )
        self.assertEqual(self.ctrl._pick_created_id(rows, before_max=100, before_ids=None), "k1eeeeee")

    def test_two_sequential_picks_never_collide(self):
        # Simulate two creates against a view that (due to a glitch) shows both
        # new rows to both. With registration between picks, they resolve to
        # distinct ids.
        before_ids = {"k1old000"}
        rows = _rows(
            (100, "k1old000", "Snapchat:"),
            (101, "k1new111", "Snapchat:"),
            (102, "k1new222", "Snapchat:"),
        )
        first = self.ctrl._pick_created_id(rows, before_max=100, before_ids=before_ids)
        adspower_ui._remember_assigned_id(first)
        second = self.ctrl._pick_created_id(rows, before_max=100, before_ids=before_ids)
        self.assertNotEqual(first, second)
        self.assertEqual({first, second}, {"k1new111", "k1new222"})


if __name__ == "__main__":
    unittest.main()
