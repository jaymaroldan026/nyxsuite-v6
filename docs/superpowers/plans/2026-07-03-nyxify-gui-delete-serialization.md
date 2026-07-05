# Nyxify GUI Delete Serialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent concurrent no-API AdsPower GUI delete flows from fighting over the same dialog and stranding Nyxify rows at `cleanup_delete_failed`.

**Architecture:** Keep the fix inside `AdsPowerUIController.delete_profile_by_id`, matching the existing GUI lock boundaries used by create, open, close, and rename. Add focused unit coverage that proves delete acquires the global GUI lock before touching row visibility, selection, dialogs, and row-gone verification.

**Tech Stack:** Python `unittest`, existing AdsPower GUI controller helpers, existing cross-process `_GUI_LOCK`.

---

### Task 1: Serialize No-API Delete

**Files:**
- Modify: `tests/test_adspower_open_batch.py`
- Modify: `core/adspower_ui.py`

- [x] **Step 1: Write the failing test**

Add a test that replaces `core.adspower_ui._GUI_LOCK` with a recording lock, calls `delete_profile_by_id`, and asserts GUI work starts only after lock entry:

```python
class DeleteProfileLockTests(unittest.TestCase):
    def test_delete_profile_runs_full_gui_flow_under_global_lock(self):
        events = []

        class RecordingLock:
            def __enter__(self):
                events.append("enter")

            def __exit__(self, *_exc):
                events.append("exit")
                return False

        ctrl = AdsPowerUIController.__new__(AdsPowerUIController)
        ctrl._ensure_row_visible = mock.Mock(side_effect=lambda _pid: events.append("visible") or True)
        ctrl._row_has_button = mock.Mock(return_value=False)
        ctrl._click_row_menu_delete = mock.Mock(side_effect=lambda _pid: events.append("delete-click") or True)
        ctrl._connect = mock.Mock()
        ctrl._find = mock.Mock(return_value=object())
        ctrl._tick_clear_cache = mock.Mock()
        ctrl._maybe_confirm = mock.Mock(return_value=True)
        ctrl._row_center_y = mock.Mock(side_effect=[240, None])

        with mock.patch.object(aui, "_GUI_LOCK", RecordingLock()), \
             mock.patch.object(aui.time, "sleep", lambda *_args, **_kwargs: None):
            self.assertEqual(
                ctrl.delete_profile_by_id("k1delete"),
                {"code": 0, "deleted": True, "profile_id": "k1delete"},
            )

        self.assertEqual(events, ["enter", "visible", "delete-click", "exit"])
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_adspower_open_batch.DeleteProfileLockTests.test_delete_profile_runs_full_gui_flow_under_global_lock -v
```

Expected: fails because `visible` is recorded before `enter`.

- [x] **Step 3: Write minimal implementation**

Decorate `AdsPowerUIController.delete_profile_by_id` with the existing global GUI serializer:

```python
@_serialized
def delete_profile_by_id(self, profile_id: str) -> dict:
    ...
```

Keep the existing delete algorithm unchanged inside that block.

- [x] **Step 4: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_adspower_open_batch.DeleteProfileLockTests.test_delete_profile_runs_full_gui_flow_under_global_lock -v
python3 -m unittest tests.test_adspower_open_batch tests.test_nyxify_cleanup -v
```

Expected: all selected tests pass.

- [x] **Step 5: Inspect diff**

Run:

```bash
git diff -- core/adspower_ui.py tests/test_adspower_open_batch.py docs/superpowers/plans/2026-07-03-nyxify-gui-delete-serialization.md
```

Expected: only the plan, the focused regression test, and the delete lock change appear.
