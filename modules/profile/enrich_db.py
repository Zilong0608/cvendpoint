from __future__ import annotations

import re
from typing import Tuple, List

from modules.shared.logging import get_logger
from .db import get_course_rows
from .schemas import Course

logger = get_logger("profile.enrich_db")


COURSE_CODE_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{3,4}\s?-?\d{4}(?![A-Z0-9])")


def _find_codes(text: str) -> list[str]:
    if not text:
        return []
    seen = set()
    out: list[str] = []
    for m in COURSE_CODE_RE.finditer(text.upper()):
        code = (m.group(0) or "").replace(" ", "").replace("-", "")
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _topics_skills_from_text(text: str) -> Tuple[list[str], list[str]]:
    topics: list[str] = []
    for ln in text.splitlines():
        raw = ln.strip()
        s = raw.lstrip("-•–· ")
        if len(s) > 4 and (raw.startswith("-") or raw.startswith("•")):
            topics.append(s)
    # dedup + cap
    seen = set()
    tuniq: list[str] = []
    for t in topics:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        tuniq.append(t)
        if len(tuniq) >= 20:
            break

    TOKENS = [
        "algorithms", "data structures", "graphs", "trees", "recursion", "dynamic programming", "hashing", "complexity",
        "python", "java", "c++", "c#", "sql", "tableau", "pandas", "numpy",
        "machine learning", "deep learning", "nlp", "transformer", "pytorch", "tensorflow",
        "database", "relational", "normalization", "indexing", "transactions", "concurrency", "er modeling", "query optimization",
        # AI course common terms
        "artificial intelligence", "search", "planning", "knowledge representation", "logic", "inference", "constraint satisfaction", "prolog",
    ]
    low = (text or "").lower()
    skills_set = set()
    for tok in TOKENS:
        if tok in low:
            if tok in ["sql", "nlp", "c++", "c#"]:
                skills_set.add(tok.upper())
            else:
                # Fix known brand casing
                if tok == "pytorch":
                    skills_set.add("PyTorch")
                elif tok == "tensorflow":
                    skills_set.add("TensorFlow")
                elif tok == "artificial intelligence":
                    skills_set.add("Artificial Intelligence")
                else:
                    skills_set.add(tok.title())
    return tuniq, sorted(skills_set)


def _canonicalize_skill_phrases(tokens: List[str], *, limit: int = 6) -> List[str]:
    pres = {t.lower(): t for t in tokens}
    out: list[str] = []

    def has(k: str) -> bool:
        return k in pres

    # combine pairs
    if has("algorithms") and has("data structures"):
        out.append("Algorithms & Data Structures")
        pres.pop("algorithms", None); pres.pop("data structures", None)
    if has("algorithms") and has("complexity"):
        out.append("Algorithmic Complexity")
        pres.pop("algorithms", None); pres.pop("complexity", None)
    g = has("graphs"); t = has("trees")
    if g and t:
        out.append("Graph/Tree Algorithms")
        pres.pop("graphs", None); pres.pop("trees", None)
    elif g:
        out.append("Graph Algorithms"); pres.pop("graphs", None)
    elif t:
        out.append("Tree Algorithms"); pres.pop("trees", None)
    if has("python") and has("numpy"):
        out.append("Python + NumPy")
        pres.pop("python", None); pres.pop("numpy", None)

    # single prominent phrases
    if has("dynamic programming"):
        out.append("Dynamic Programming"); pres.pop("dynamic programming", None)
    if has("recursion"):
        out.append("Recursion"); pres.pop("recursion", None)
    if has("machine learning"):
        out.append("Machine Learning"); pres.pop("machine learning", None)
    if has("sql"):
        out.append("SQL"); pres.pop("sql", None)
    if has("nlp"):
        out.append("NLP"); pres.pop("nlp", None)
    if has("c++"):
        out.append("C++"); pres.pop("c++", None)

    # fill remaining by priority
    priority = [
        "python", "data structures", "algorithms", "complexity", "graphs", "trees",
        "pandas", "numpy", "tableau", "deep learning", "pytorch", "tensorflow",
    ]
    for key in priority:
        if key in pres:
            val = pres.pop(key)
            out.append(val if val.isupper() else val.title())
        if len(out) >= limit:
            break

    # dedup + cap
    seen = set(); final: list[str] = []
    for s in out:
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        final.append(s)
        if len(final) >= limit:
            break
    return final


def enrich_courses_from_text_db(texts: list[str], *, extra_codes: list[str] | None = None):
    notes: list[str] = ["provider:db"]
    all_text = "\n".join([t for t in (texts or []) if t])
    codes = _find_codes(all_text)
    if extra_codes:
        for c in extra_codes:
            cc = (c or "").upper().replace(" ", "").replace("-", "")
            if cc and cc not in codes:
                codes.append(cc)
    if not codes:
        return [], notes + ["no_course_codes"]

    rows = get_course_rows(codes[:10])
    courses: list[Course] = []
    for code in codes[:10]:
        row = rows.get(code)
        if not row:
            notes.append("miss:" + code)
            courses.append(Course(code=code, name=None, topics=[], skills=[], tools=[]))
            continue
        _, skills_tokens = _topics_skills_from_text(row.description or "")
        phrases = _canonicalize_skill_phrases(skills_tokens, limit=6)
        courses.append(Course(code=code, name=None, topics=[], skills=phrases, tools=[]))
        notes.append("hit:" + code)
    return courses, notes
