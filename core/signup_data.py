# PEP 563: keep annotations as strings so 3.10+ union syntax (e.g. "Path | None")
# is not evaluated at runtime - macOS ships Python 3.9, which would otherwise
# raise "unsupported operand type(s) for |" on import.
from __future__ import annotations

import random
import shutil
import sys
from pathlib import Path

from core.process_utils import APP_DATA_DIR, ROOT_DIR


SOURCE_SIGNUP_NAMES_DIR = ROOT_DIR / "data" / "signup_names"
PACKAGED_SIGNUP_NAMES_TEMPLATE_DIR = ROOT_DIR / "defaults" / "signup_names"
LEGACY_SIGNUP_NAMES_DIR = APP_DATA_DIR / "data" / "signup_names"
DEFAULT_SIGNUP_NAMES_DIR = SOURCE_SIGNUP_NAMES_DIR if getattr(sys, "frozen", False) else LEGACY_SIGNUP_NAMES_DIR

_MODEL_ALIASES: dict[str, str] = {
    "debbie": "Debbie",
    "deborah": "Debbie",
    "debora": "Debbie",
}

BIRTH_YEARS: dict[str, str] = {
    "alicia": "2001",
    "willow": "2004",
    "nina": "2006",
    "chloe": "2004",
    "lizzie": "1998",
    "emily": "2000",
    "clea": "2008",
    "debbie": "2008",
    "tessa": "2008",
    "jade": "2001",
    "olivia": "2007",
}


def resolve_model_name(model: str) -> str:
    key = model.strip().lower()
    return _MODEL_ALIASES.get(key, model.strip())


def ensure_signup_names_dir(root_dir: Path | None = None) -> Path:
    target_dir = Path(root_dir or DEFAULT_SIGNUP_NAMES_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)

    template_dirs = [PACKAGED_SIGNUP_NAMES_TEMPLATE_DIR]
    if SOURCE_SIGNUP_NAMES_DIR.resolve() != target_dir.resolve():
        template_dirs.append(SOURCE_SIGNUP_NAMES_DIR)
    if LEGACY_SIGNUP_NAMES_DIR.resolve() != target_dir.resolve():
        template_dirs.append(LEGACY_SIGNUP_NAMES_DIR)

    for template_dir in template_dirs:
        if not template_dir.exists():
            continue
        for source in template_dir.glob("*.txt"):
            target = target_dir / source.name
            if not target.exists():
                shutil.copy2(source, target)
    return target_dir


def get_random_name(model: str, names_dir: Path) -> str:
    resolved = resolve_model_name(model)
    names_dir = ensure_signup_names_dir(names_dir)
    name_file = names_dir / f"{resolved}.txt"
    if not name_file.exists():
        return ""
    lines = []
    for line in name_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(";") and not stripped.startswith("#"):
            lines.append(stripped)
    return random.choice(lines) if lines else ""


def generate_birthday(model: str) -> dict:
    resolved = resolve_model_name(model)
    key = resolved.lower()
    year = BIRTH_YEARS.get(key, "2001")
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return {"month": month, "day": day, "year": year}
