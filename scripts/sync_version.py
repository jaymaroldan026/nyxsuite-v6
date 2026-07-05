"""Rewrite extension manifest.json `version` fields from `core.version`.

Run after bumping `core/version.py` (or from the packaging build scripts).
This is the only place that knows manifest.json's structure — the rest of
the codebase reads `NYX_VERSION` / `NYXIFY_VERSION` directly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.version import NYX_VERSION, NYXIFY_VERSION  # noqa: E402


VERSION_FIELD_RE = re.compile(r'("version"\s*:\s*")([^"]*)(")')
VERSION_NAME_FIELD_RE = re.compile(r'("version_name"\s*:\s*")([^"]*)(")')


def rewrite_manifest(path: Path, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, count = VERSION_FIELD_RE.subn(
        lambda m: f'{m.group(1)}{version}{m.group(3)}', text, count=1
    )
    if count == 0:
        raise RuntimeError(f"No version field found in {path}")
    new_text, name_count = VERSION_NAME_FIELD_RE.subn(
        lambda m: f'{m.group(1)}{version}{m.group(3)}', new_text, count=1
    )
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    targets = [
        (ROOT / "nyx_extension" / "manifest.json", NYX_VERSION),
        (ROOT / "nyxify_extension" / "manifest.json", NYXIFY_VERSION),
    ]
    for path, version in targets:
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        changed = rewrite_manifest(path, version)
        action = "updated" if changed else "unchanged"
        print(f"{action}: {path} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
