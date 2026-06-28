"""Bulk-open / bulk-close coalescing + bulk-search query formatting for the
no-API GUI path.

These cover the pure logic of ``core.adspower_ui._GuiBatcher`` and
``_search_by_ids`` without driving a real AdsPower window:

* ``_search_by_ids`` joins the ids with spaces and applies the ``Profile ID``/
  ``is`` filter (the native bulk-ID search).
* concurrent opens/closes coalesce into ONE bulk search (the leader drains every
  other waiting caller) and each caller's result resolves independently, with
  the action's return value (close's bool) carried back to that caller.

``_GUI_LOCK`` is patched to a plain re-entrant lock so the test never contends
with a real running suite's named mutex.
"""
import threading
import unittest
from unittest import mock

import core.adspower_ui as aui
from core.adspower_ui import AdsPowerUIController, AdsPowerUIError, _GuiBatcher


class _FakeController:
    """Stands in for AdsPowerUIController: records each bulk batch and resolves
    every id's result the way the real ``_bulk_*_locked`` methods do."""

    def __init__(self, fail_ids=()):
        self.batches = []
        self._fail = set(fail_ids)
        self._lock = threading.Lock()

    def _bulk_open_locked(self, ids, results):
        self._record(ids, results, value=None)

    def _bulk_close_locked(self, ids, results):
        self._record(ids, results, value=True)   # close returns a bool

    def _record(self, ids, results, value):
        with self._lock:
            self.batches.append(list(ids))
        for pid in ids:
            res = results[pid]
            if pid in self._fail:
                res.ok, res.error = False, RuntimeError(f"boom {pid}")
            else:
                res.ok, res.value = True, value
            res.event.set()


class SearchByIdsTests(unittest.TestCase):
    def _bare_controller(self):
        # __new__ bypasses __init__ (which requires pywinauto) — we only exercise
        # _search_by_ids, stubbing the _search_by it delegates to.
        return AdsPowerUIController.__new__(AdsPowerUIController)

    def test_builds_space_joined_profile_id_query(self):
        ctrl = self._bare_controller()
        calls = []
        ctrl._search_by = lambda value, field, operator: calls.append((value, field, operator))

        ctrl._search_by_ids(["k1a", " k1b ", "", "k1c"])

        self.assertEqual(calls, [("k1a k1b k1c", "Profile ID", "is")])

    def test_single_id_is_a_one_element_bulk_search(self):
        ctrl = self._bare_controller()
        calls = []
        ctrl._search_by = lambda value, field, operator: calls.append((value, field, operator))

        ctrl._search_by_ids(["k1solo"])

        self.assertEqual(calls, [("k1solo", "Profile ID", "is")])

    def test_requires_at_least_one_id(self):
        ctrl = self._bare_controller()
        ctrl._search_by = lambda *a, **k: None
        with self.assertRaises(AdsPowerUIError):
            ctrl._search_by_ids(["", "   "])


class GuiBatcherTests(unittest.TestCase):
    def setUp(self):
        # Hermetic GUI lock — never touch the real cross-process named mutex.
        self._patch = mock.patch.object(aui, "_GUI_LOCK", threading.RLock())
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _run_concurrently(self, batcher, fake, ids):
        results = {}
        barrier = threading.Barrier(len(ids))

        def worker(pid):
            barrier.wait()              # all callers hit submit() at once
            try:
                results[pid] = ("ok", batcher.submit(fake, pid))
            except Exception as exc:    # noqa: BLE001 - record per-caller failure
                results[pid] = ("err", str(exc))

        threads = [threading.Thread(target=worker, args=(pid,)) for pid in ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            self.assertFalse(t.is_alive(), "a submit() never returned")
        return results

    def test_concurrent_opens_share_one_bulk_search(self):
        batcher = _GuiBatcher("_bulk_open_locked", "open")
        fake = _FakeController()
        ids = [f"k1id{i}" for i in range(5)]

        results = self._run_concurrently(batcher, fake, ids)

        self.assertEqual({pid: results[pid][0] for pid in ids}, {pid: "ok" for pid in ids})
        # The headline win: five opens, ONE search.
        self.assertEqual(len(fake.batches), 1)
        self.assertCountEqual(fake.batches[0], ids)

    def test_concurrent_closes_share_one_bulk_search_and_return_value(self):
        batcher = _GuiBatcher("_bulk_close_locked", "close")
        fake = _FakeController()
        ids = [f"k1cl{i}" for i in range(4)]

        results = self._run_concurrently(batcher, fake, ids)

        # Each caller gets close's bool back, and four closes cost ONE search.
        self.assertEqual(results, {pid: ("ok", True) for pid in ids})
        self.assertEqual(len(fake.batches), 1)
        self.assertCountEqual(fake.batches[0], ids)

    def test_per_id_failure_only_fails_that_caller(self):
        batcher = _GuiBatcher("_bulk_open_locked", "open")
        fake = _FakeController(fail_ids={"k1bad"})
        ids = ["k1ok1", "k1bad", "k1ok2"]

        results = self._run_concurrently(batcher, fake, ids)

        self.assertEqual(results["k1ok1"][0], "ok")
        self.assertEqual(results["k1ok2"][0], "ok")
        self.assertEqual(results["k1bad"][0], "err")
        self.assertIn("boom k1bad", results["k1bad"][1])
        # Still one batch — the bad id didn't sink the others.
        self.assertEqual(len(fake.batches), 1)
        self.assertCountEqual(fake.batches[0], ids)


if __name__ == "__main__":
    unittest.main()
