from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, Optional, Iterable

from modules.shared.cache import TTLCache
from modules.shared.logging import get_logger

logger = get_logger("profile.db")


@dataclass
class CourseRow:
    code: str
    university: str
    link: str
    description: str


_DB_CACHE = TTLCache(ttl_seconds=600)  # 10 min cache of parsed CSVs


def _norm_code(code: str) -> str:
    return (code or "").upper().replace(" ", "").replace("-", "")


def _load_db(root: str = "database") -> Dict[str, CourseRow]:
    cached = _DB_CACHE.get("courses")
    if cached:
        return cached  # type: ignore

    rows: Dict[str, CourseRow] = {}
    if not os.path.isdir(root):
        logger.info("database folder not found; skipping course DB load")
        _DB_CACHE.set("courses", rows)
        return rows

    for name in os.listdir(root):
        if not name.lower().endswith(".csv"):
            continue
        path = os.path.join(root, name)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    code = _norm_code((r.get("code") or "").strip())
                    if not code:
                        continue
                    row = CourseRow(
                        code=code,
                        university=(r.get("university") or "").strip(),
                        link=(r.get("link") or "").strip(),
                        description=(r.get("description") or "").strip(),
                    )
                    # First one wins; later files won't override
                    rows.setdefault(code, row)
        except Exception as e:
            logger.warning(f"failed to read CSV {path}: {e}")

    _DB_CACHE.set("courses", rows)
    logger.info(f"course DB loaded: {len(rows)} rows")
    return rows


def get_course_row(code: str) -> Optional[CourseRow]:
    code_n = _norm_code(code)
    db = _load_db()
    return db.get(code_n)


def get_course_rows(codes: Iterable[str]) -> Dict[str, CourseRow]:
    db = _load_db()
    out: Dict[str, CourseRow] = {}
    for c in codes:
        rc = db.get(_norm_code(c))
        if rc:
            out[rc.code] = rc
    return out

