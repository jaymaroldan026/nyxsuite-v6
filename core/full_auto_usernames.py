import random
import re
import shutil
import sys
import threading
import uuid
from pathlib import Path

from core.process_utils import APP_DATA_DIR, ROOT_DIR
from core.signup_data import resolve_model_name


SOURCE_FULL_AUTO_USERNAMES_DIR = ROOT_DIR / "data" / "full_auto_usernames"
PACKAGED_FULL_AUTO_USERNAMES_TEMPLATE_DIR = ROOT_DIR / "defaults" / "full_auto_usernames"
LEGACY_FULL_AUTO_USERNAMES_DIR = APP_DATA_DIR / "data" / "full_auto_usernames"
DEFAULT_FULL_AUTO_USERNAMES_DIR = SOURCE_FULL_AUTO_USERNAMES_DIR if getattr(sys, "frozen", False) else LEGACY_FULL_AUTO_USERNAMES_DIR
TEMP_USERNAME_RE = re.compile(r"^temp(?:[_-].+|\d.*)?$", re.IGNORECASE)


def is_temp_username(value):
    return bool(TEMP_USERNAME_RE.fullmatch(str(value or "").strip()))


def _normalize_username(value):
    return str(value or "").strip().lower()


def _sanitize_model_name(model):
    resolved = resolve_model_name(str(model or ""))
    cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "", str(resolved or "").strip()).strip(" ._-")
    return cleaned


def _is_data_line(line):
    stripped = str(line or "").strip()
    return bool(stripped and not stripped.startswith("#") and not stripped.startswith(";"))


class FullAutoUsernameStore:
    def __init__(self, root_dir=None):
        self.root_dir = Path(root_dir or DEFAULT_FULL_AUTO_USERNAMES_DIR)
        self.legacy_root_dir = Path(LEGACY_FULL_AUTO_USERNAMES_DIR)
        self.template_root_dir = Path(PACKAGED_FULL_AUTO_USERNAMES_TEMPLATE_DIR)
        self._lock = threading.Lock()
        self._reservations = {}

    def ensure_model_files(self):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for source_dir in [self.template_root_dir, SOURCE_FULL_AUTO_USERNAMES_DIR]:
            try:
                same_dir = source_dir.resolve() == self.root_dir.resolve()
            except Exception:
                same_dir = False
            if same_dir or not source_dir.exists():
                continue
            for source in source_dir.glob("*.txt"):
                target = self.root_dir / source.name
                if not target.exists():
                    shutil.copy2(source, target)

    def _legacy_model_file(self, target_name):
        if self.legacy_root_dir == self.root_dir:
            return None
        for existing in self.legacy_root_dir.glob("*.txt"):
            if existing.name.lower() == target_name.lower():
                return existing
        return None

    def _model_file(self, model):
        safe_model = _sanitize_model_name(model)
        if not safe_model:
            raise ValueError("Model is required for Full Auto Mode username lookup.")

        self.root_dir.mkdir(parents=True, exist_ok=True)
        target_name = f"{safe_model}.txt"
        for existing in self.root_dir.glob("*.txt"):
            if existing.name.lower() == target_name.lower():
                return existing
        path = self.root_dir / target_name
        if not path.exists():
            legacy_path = self._legacy_model_file(target_name)
            if legacy_path and legacy_path.exists():
                shutil.copy2(legacy_path, path)
            else:
                path.write_text("", encoding="utf-8")
        return path

    @staticmethod
    def _read_lines(path):
        try:
            return path.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            return []

    def _reserved_usernames(self, except_row_key=""):
        skip_row_key = str(except_row_key or "").strip()
        return {
            _normalize_username(payload.get("username"))
            for row_key, payload in self._reservations.items()
            if row_key != skip_row_key and _normalize_username(payload.get("username"))
        }

    def reserve(self, row_key, model, current_username="", reason=""):
        normalized_row_key = str(row_key or "").strip()
        if not normalized_row_key:
            raise ValueError("Row key is required for Full Auto Mode username reservation.")

        with self._lock:
            existing = self._reservations.get(normalized_row_key)
            if existing:
                return {
                    "reserved": True,
                    "reservation_id": existing["reservation_id"],
                    "row_key": normalized_row_key,
                    "model": existing["model"],
                    "username": existing["username"],
                    "file": str(existing["file"]),
                }

            path = self._model_file(model)
            reserved = self._reserved_usernames(except_row_key=normalized_row_key)
            available = [
                line.strip()
                for line in self._read_lines(path)
                if _is_data_line(line) and _normalize_username(line) not in reserved
            ]
            if not available:
                return {
                    "reserved": False,
                    "row_key": normalized_row_key,
                    "model": str(model or "").strip(),
                    "username": "",
                    "file": str(path),
                    "available": 0,
                }

            username = random.choice(available)
            reservation = {
                "reservation_id": uuid.uuid4().hex,
                "row_key": normalized_row_key,
                "model": str(model or "").strip(),
                "username": username,
                "current_username": str(current_username or "").strip(),
                "reason": str(reason or "").strip(),
                "file": path,
            }
            self._reservations[normalized_row_key] = reservation
            return {
                "reserved": True,
                "reservation_id": reservation["reservation_id"],
                "row_key": normalized_row_key,
                "model": reservation["model"],
                "username": username,
                "file": str(path),
            }

    def _remove_username_from_file(self, path, username):
        target = _normalize_username(username)
        if not target:
            return False

        lines = self._read_lines(path)
        next_lines = []
        removed = False
        for line in lines:
            if not removed and _is_data_line(line) and _normalize_username(line) == target:
                removed = True
                continue
            next_lines.append(line)

        if removed:
            path.write_text("\n".join(next_lines) + ("\n" if next_lines else ""), encoding="utf-8")
        return removed

    def commit(self, row_key, reservation_id="", username="", model="", success=False, error=""):
        normalized_row_key = str(row_key or "").strip()
        if not normalized_row_key:
            raise ValueError("Row key is required for Full Auto Mode username commit.")

        with self._lock:
            reservation = self._reservations.get(normalized_row_key)
            if reservation_id and reservation and reservation.get("reservation_id") != str(reservation_id).strip():
                raise ValueError("Full Auto Mode reservation id does not match the pending username.")

            resolved_username = str(username or (reservation or {}).get("username") or "").strip()
            resolved_model = str(model or (reservation or {}).get("model") or "").strip()
            removed = False

            if success:
                if reservation:
                    removed = self._remove_username_from_file(Path(reservation["file"]), resolved_username)
                elif resolved_model and resolved_username:
                    removed = self._remove_username_from_file(self._model_file(resolved_model), resolved_username)

            if reservation:
                self._reservations.pop(normalized_row_key, None)

            return {
                "success": bool(success),
                "row_key": normalized_row_key,
                "username": resolved_username,
                "model": resolved_model,
                "removed": removed,
                "released": not bool(success),
                "error": str(error or "").strip(),
            }
