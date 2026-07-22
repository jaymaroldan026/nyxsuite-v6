import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.process_utils import APP_DATA_DIR
from core.nyx_runtime_config import load_nyx_config

DATA_DIR = APP_DATA_DIR / "data"
DB_PATH = DATA_DIR / "bitmoji_tasks.db"
PRUNE_DONE_KEEP = 150
CONTINUOUS_TASK_PRIORITY = 100


def utc_now_iso():

    return datetime.now(timezone.utc).isoformat()


class TaskStore:

    def __init__(self, db_path=None):

        self.db_path = str(db_path or DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self):

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL,
                    gender TEXT NOT NULL DEFAULT 'female',
                    outfit_seed TEXT DEFAULT '',
                    source TEXT DEFAULT 'ui',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    priority INTEGER NOT NULL DEFAULT 0,
                    run_token TEXT DEFAULT '',
                    last_step TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                str(row["name"]).strip().lower()
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "source" not in existing_columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'ui'")
            if "username" not in existing_columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN username TEXT NOT NULL DEFAULT ''")
            if "password" not in existing_columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN password TEXT NOT NULL DEFAULT ''")
            if "run_token" not in existing_columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN run_token TEXT DEFAULT ''")
            if "priority" not in existing_columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS done_profiles (
                    profile_id TEXT PRIMARY KEY,
                    model TEXT DEFAULT '',
                    marked_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS missing_profiles (
                    profile_id TEXT PRIMARY KEY,
                    model TEXT DEFAULT '',
                    marked_at TEXT NOT NULL
                )
                """
            )

    def _should_ignore_done_profiles(self):
        return bool(load_nyx_config().get("ignore_done_profiles", True))

    def _is_archived_done_profile(self, conn, profile_id):
        archived = conn.execute(
            """
            SELECT profile_id
            FROM done_profiles
            WHERE profile_id = ?
            """,
            (profile_id,)
        ).fetchone()
        return archived is not None

    def _is_archived_missing_profile(self, conn, profile_id):
        archived = conn.execute(
            """
            SELECT profile_id
            FROM missing_profiles
            WHERE profile_id = ?
            """,
            (profile_id,)
        ).fetchone()
        return archived is not None

    def _delete_old_done_tasks(self, conn, keep=PRUNE_DONE_KEEP):
        done_count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE status = 'DONE'"
        ).fetchone()
        done_count = int(done_count_row["count"] or 0) if done_count_row else 0
        safe_keep = max(0, int(keep or PRUNE_DONE_KEEP))
        excess_count = max(0, done_count - safe_keep)
        if excess_count <= 0:
            return 0, done_count, done_count

        cursor = conn.execute(
            """
            DELETE FROM tasks
            WHERE id IN (
                SELECT id
                FROM tasks
                WHERE status = 'DONE'
                ORDER BY
                    COALESCE(NULLIF(completed_at, ''), updated_at, created_at) ASC,
                    id ASC
                LIMIT ?
            )
            """,
            (excess_count,)
        )
        deleted = int(cursor.rowcount or 0)
        return deleted, done_count, max(0, done_count - deleted)

    def get_pending_tasks(self):

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, profile_id, username, model, gender, outfit_seed, source, status, priority,
                       last_step, error, completed_at, created_at, updated_at
                FROM tasks
                WHERE status = 'PENDING'
                ORDER BY priority DESC, updated_at ASC, id ASC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def list_tasks(self, limit=100):

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, profile_id, username,
                       CASE WHEN TRIM(COALESCE(password, '')) <> '' THEN 1 ELSE 0 END AS has_password,
                       model, gender, source, status, priority, run_token, last_step, error, completed_at, created_at, updated_at
                FROM tasks
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

        return [dict(row) for row in rows]

    def upsert_task(
        self,
        profile_id,
        model,
        gender="female",
        status="PENDING",
        outfit_seed="",
        ignore_done_override=None,
        source="ui",
        username="",
        password="",
        priority=0,
    ):

        now = utc_now_iso()
        normalized_username = str(username or "").strip()
        normalized_password = str(password or "").strip()
        try:
            normalized_priority = max(0, int(priority or 0))
        except Exception:
            normalized_priority = 0

        with self._connect() as conn:
            should_ignore_done = self._should_ignore_done_profiles() if ignore_done_override is None else bool(ignore_done_override)
            if should_ignore_done and self._is_archived_done_profile(conn, profile_id):
                return None, "ignored_done"
            if should_ignore_done and self._is_archived_missing_profile(conn, profile_id):
                return None, "ignored_missing"

            existing = conn.execute(
                """
                SELECT id, status, run_token, last_step, error, completed_at, model, gender, outfit_seed, source, username, password, priority
                FROM tasks
                WHERE profile_id = ?
                """,
                (profile_id,)
            ).fetchone()

            if existing:
                existing_status = str(existing["status"] or "").strip().upper()
                should_requeue_done = (
                    not should_ignore_done
                    and existing_status == "DONE"
                )

                next_status = existing["status"] or status
                next_run_token = existing["run_token"] or ""
                next_last_step = existing["last_step"] or ""
                next_error = existing["error"] or ""
                next_completed_at = existing["completed_at"] or ""
                next_username = normalized_username or str(existing["username"] or "").strip()
                next_password = normalized_password or str(existing["password"] or "").strip()
                existing_source = str(existing["source"] or "").strip()
                try:
                    existing_priority = int(existing["priority"] or 0)
                except Exception:
                    existing_priority = 0
                next_priority = max(existing_priority, normalized_priority)
                next_source = source
                preserve_active_continuous = (
                    existing_status in {"PENDING", "RUNNING"}
                    and existing_source.lower() == "nyxify_continuous"
                    and str(source or "").strip().lower() != "nyxify_continuous"
                    and existing_priority >= normalized_priority
                )
                if preserve_active_continuous:
                    next_source = existing_source
                    next_username = str(existing["username"] or "").strip() or normalized_username
                    next_password = str(existing["password"] or "").strip() or normalized_password

                if should_requeue_done:
                    next_status = status
                    next_run_token = ""
                    next_last_step = ""
                    next_error = ""
                    next_completed_at = ""
                    next_priority = normalized_priority
                    next_source = source
                    conn.execute(
                        "DELETE FROM done_profiles WHERE profile_id = ?",
                        (profile_id,)
                    )

                # Keep the existing workflow state for already-known profiles so
                # repeated extension detections do not re-queue the same ID.
                conn.execute(
                    """
                    UPDATE tasks
                    SET username = ?, password = ?, model = ?, gender = ?, outfit_seed = ?, source = ?,
                        status = ?, priority = ?, run_token = ?, last_step = ?, error = ?, completed_at = ?, updated_at = ?
                    WHERE profile_id = ?
                    """,
                    (
                        next_username,
                        next_password,
                        model,
                        gender,
                        outfit_seed,
                        next_source,
                        next_status,
                        next_priority,
                        next_run_token,
                        next_last_step,
                        next_error,
                        next_completed_at,
                        now,
                        profile_id,
                    )
                )
                return existing["id"], "updated"

            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    profile_id, username, password, model, gender, outfit_seed, source, status, priority, run_token, last_step, error, completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', ?, ?)
                """,
                (
                    profile_id,
                    normalized_username,
                    normalized_password,
                    model,
                    gender,
                    outfit_seed,
                    source,
                    status,
                    normalized_priority,
                    now,
                    now,
                )
            )
            return cursor.lastrowid, "created"

    def begin_run(self, task_id, run_token, step="opening_profile"):
        now = utc_now_iso()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'RUNNING',
                    run_token = ?,
                    last_step = ?,
                    error = '',
                    completed_at = '',
                    updated_at = ?
                WHERE id = ?
                  AND status = 'PENDING'
                """,
                (run_token, step, now, task_id)
            )
            return cursor.rowcount > 0

    def is_current_run(self, task_id, run_token):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_token FROM tasks WHERE id = ?",
                (task_id,)
            ).fetchone()

        if not row:
            return False

        return str(row["run_token"] or "") == str(run_token or "")

    def update_status(self, task_id, status, step=None, error=None, run_token=None):

        now = utc_now_iso()
        completed_at = now if status == "DONE" else None

        with self._connect() as conn:
            current = conn.execute(
                "SELECT profile_id, model, run_token, last_step, error, completed_at FROM tasks WHERE id = ?",
                (task_id,)
            ).fetchone()

            if not current:
                return False

            if run_token is not None and str(current["run_token"] or "") != str(run_token or ""):
                return False

            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    run_token = ?,
                    last_step = ?,
                    error = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    "" if status in {"DONE", "FAILED", "PENDING"} else current["run_token"],
                    step if step is not None else current["last_step"],
                    error if error is not None else current["error"],
                    completed_at if completed_at is not None else current["completed_at"],
                    now,
                    task_id,
                )
            )

            if status == "DONE":
                conn.execute(
                    """
                    INSERT INTO done_profiles (profile_id, model, marked_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET model = excluded.model, marked_at = excluded.marked_at
                    """,
                    (current["profile_id"], current["model"], now)
                )
            return True

    def update_last_step(self, task_id, step, run_token=None):

        now = utc_now_iso()

        with self._connect() as conn:
            if run_token is not None:
                row = conn.execute(
                    "SELECT run_token FROM tasks WHERE id = ?",
                    (task_id,)
                ).fetchone()
                if not row or str(row["run_token"] or "") != str(run_token or ""):
                    return False

            conn.execute(
                """
                UPDATE tasks
                SET last_step = ?, updated_at = ?
                WHERE id = ?
                """,
                (step, now, task_id)
            )
            return True

    def update_error(self, task_id, error_message):

        now = utc_now_iso()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error_message, now, task_id)
            )

    def get_failed_tasks(self):

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT profile_id, model
                FROM tasks
                WHERE status = 'FAILED'
                ORDER BY updated_at DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def reset_failed_tasks(self):

        now = utc_now_iso()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING', run_token = '', error = '', last_step = '', updated_at = ?
                WHERE status = 'FAILED'
                """,
                (now,)
            )
            return cursor.rowcount

    def clear_completed_tasks(self):
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE status = 'DONE'"
            )
            return cursor.rowcount

    def prune_completed_tasks_keep_latest(self, keep=PRUNE_DONE_KEEP):
        with self._connect() as conn:
            deleted, before_count, after_count = self._delete_old_done_tasks(conn, keep=keep)
            return {
                "deleted": deleted,
                "before": before_count,
                "after": after_count,
                "keep": max(0, int(keep or PRUNE_DONE_KEEP)),
            }

    def reset_stuck_tasks(self):
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING', run_token = '', last_step = '', error = '', updated_at = ?
                WHERE status = 'RUNNING'
                """,
                (now,)
            )
            return cursor.rowcount

    def clear_all_tasks(self):
        with self._connect() as conn:
            task_cursor = conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM done_profiles")
            conn.execute("DELETE FROM missing_profiles")
            return task_cursor.rowcount

    def update_status_by_profile_id(self, profile_id, status, step=None, error=None):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM tasks WHERE profile_id = ?",
                (profile_id,)
            ).fetchone()

        if not row:
            return False

        self.update_status(row["id"], status, step=step, error=error)
        return True

    def remove_task_by_profile_id(self, profile_id):
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE profile_id = ?",
                (profile_id,)
            )
            return cursor.rowcount

    def archive_missing_profile(self, profile_id, model=""):
        """Record ``profile_id`` in the missing-profiles archive so extension
        syncs skip it on upsert (``ignored_missing``). The queue row — if any —
        is left untouched."""
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_profile_id:
            return False
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT model FROM tasks WHERE profile_id = ?",
                (normalized_profile_id,)
            ).fetchone()
            archived_model = str(model or "").strip() or (str(row["model"] or "") if row else "")
            conn.execute(
                """
                INSERT INTO missing_profiles (profile_id, model, marked_at)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET model = excluded.model, marked_at = excluded.marked_at
                """,
                (normalized_profile_id, archived_model, now)
            )
            return True

    def purge_deleted_profile(self, profile_id, model=""):
        """The AdsPower profile was deleted (Nyxify cleanup/retry or a Replace
        action): drop any queue row for it AND archive the id so extension
        syncs can never re-queue it — a deleted profile would only ever run
        into a profile_missing failure.

        Returns the number of queue rows removed."""
        normalized_profile_id = str(profile_id or "").strip()
        if not normalized_profile_id:
            return 0
        self.archive_missing_profile(normalized_profile_id, model=model)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE profile_id = ?",
                (normalized_profile_id,)
            )
            return cursor.rowcount

    def remove_missing_profile_tasks(self, limit=None):
        now = utc_now_iso()
        limit_value = None
        if limit is not None:
            try:
                limit_value = max(1, int(limit))
            except Exception:
                limit_value = 1

        with self._connect() as conn:
            query = """
                SELECT id, profile_id, model, gender, source, status, run_token, last_step, error, completed_at, created_at, updated_at
                FROM tasks
                WHERE status = 'FAILED'
                  AND (
                    LOWER(COALESCE(last_step, '')) = 'profile_missing'
                    OR LOWER(COALESCE(error, '')) LIKE '%profile does not exist%'
                  )
                ORDER BY updated_at DESC, id DESC
                """
            params = ()
            if limit_value is not None:
                query += "\n                LIMIT ?"
                params = (limit_value,)

            rows = conn.execute(query, params).fetchall()

            if not rows:
                return []

            conn.executemany(
                """
                INSERT INTO missing_profiles (profile_id, model, marked_at)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET model = excluded.model, marked_at = excluded.marked_at
                """,
                [(row["profile_id"], row["model"], now) for row in rows]
            )
            task_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in task_ids)
            conn.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", task_ids)
            return [dict(row) for row in rows]

    def remove_latest_missing_profile_task(self):
        rows = self.remove_missing_profile_tasks(limit=1)
        return rows[0] if rows else None

    def get_bitmoji_statuses(self, entries):
        normalized_entries = []
        seen = set()
        for entry in entries or []:
            profile_id = str((entry or {}).get("profile_id", "")).strip()
            username = str((entry or {}).get("username", "")).strip()
            if not profile_id or profile_id in seen:
                continue
            seen.add(profile_id)
            normalized_entries.append({
                "profile_id": profile_id,
                "username": username,
            })

        if not normalized_entries:
            return []

        profile_ids = [entry["profile_id"] for entry in normalized_entries]
        placeholders = ",".join("?" for _ in profile_ids)

        with self._connect() as conn:
            done_ids = set()
            for row in conn.execute(
                f"SELECT profile_id FROM done_profiles WHERE profile_id IN ({placeholders})",
                profile_ids,
            ).fetchall():
                done_ids.add(str(row["profile_id"] or "").strip())

            task_statuses = {}
            for row in conn.execute(
                f"SELECT profile_id, status FROM tasks WHERE profile_id IN ({placeholders})",
                profile_ids,
            ).fetchall():
                task_statuses[str(row["profile_id"] or "").strip()] = str(row["status"] or "").strip().upper()

        results = []
        for entry in normalized_entries:
            profile_id = entry["profile_id"]
            task_status = task_statuses.get(profile_id, "")
            has_bitmoji = profile_id in done_ids or task_status == "DONE"
            results.append({
                "profile_id": profile_id,
                "username": entry["username"],
                "has_bitmoji": has_bitmoji,
                "status": "has_bitmoji" if has_bitmoji else "not_done",
            })
        return results

    def get_task_by_profile_id(self, profile_id):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, profile_id, username, password, model, gender, source, status, priority, run_token, last_step, error, completed_at, created_at, updated_at
                FROM tasks
                WHERE profile_id = ?
                """,
                (profile_id,)
            ).fetchone()

        return dict(row) if row else None

    def has_active_continuous_handoff(self):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE LOWER(TRIM(COALESCE(source, ''))) = 'nyxify_continuous'
                  AND status IN ('PENDING', 'RUNNING')
                """
            ).fetchone()
        try:
            return int(row[0]) > 0 if row else False
        except Exception:
            return False

    def count_non_continuous_need_login_running(self):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE status = 'RUNNING'
                  AND LOWER(TRIM(COALESCE(last_step, ''))) = 'need_login'
                  AND LOWER(TRIM(COALESCE(source, ''))) <> 'nyxify_continuous'
                """
            ).fetchone()
        try:
            return max(0, int(row[0] or 0)) if row else 0
        except Exception:
            return 0

    def requeue_running_tasks_after_runner_restart(self):
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING',
                    run_token = '',
                    last_step = 'requeued_after_runner_restart',
                    error = '',
                    completed_at = '',
                    updated_at = ?
                WHERE status = 'RUNNING'
                """,
                (now,),
            )
            return cursor.rowcount

    def relaunch_task_by_profile_id(self, profile_id):
        now = utc_now_iso()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, status FROM tasks WHERE profile_id = ?",
                (profile_id,)
            ).fetchone()

            if not row:
                return "not_found"

            if str(row["status"] or "").upper() == "RUNNING":
                return "running"

            conn.execute(
                """
                UPDATE tasks
                SET status = 'PENDING',
                    run_token = '',
                    last_step = '',
                    error = '',
                    completed_at = '',
                    updated_at = ?
                WHERE profile_id = ?
                """,
                (now, profile_id)
            )
            conn.execute(
                "DELETE FROM done_profiles WHERE profile_id = ?",
                (profile_id,)
            )
            return "requeued"
