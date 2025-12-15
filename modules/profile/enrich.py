from __future__ import annotations

import re
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from modules.agent.tools import web_search
from modules.shared.cache import TTLCache
from modules.shared.logging import get_logger
from .schemas import Course

logger = get_logger("profile.enrich")

# Match course codes like COMP9313 / COMP 9313 / COMP-9313 even邻接中文
COURSE_CODE_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{3,4}\s?-?\d{4}(?![A-Z0-9])")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

_CACHE = TTLCache(ttl_seconds=86400)  # 24h cache


def _norm_code(code: str) -> str:
    return (code or "").upper().replace(" ", "").replace("-", "")


def _find_codes(text: str) -> List[str]:
    if not text:
        return []
    codes = []
    for m in COURSE_CODE_RE.finditer(text.upper()):
        code = _norm_code(m.group(0) or "")
        codes.append(code)
    # preserve order unique
    seen = set()
    out = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _is_relevant_result(code: str, r: dict, prefer_domains: list[str] | None = None) -> int:
    url = (r.get("url") or "").lower()
    title = (r.get("title") or "").lower()
    snip = (r.get("snippet") or "").lower()
    code_low = _norm_code(code).lower()
    score = 0
    # Strong: code appears in URL or title/snippet
    if code_low in url:
        score += 5
    if code_low in title or code_low in snip:
        score += 3
    # Prefer domains
    for d in (prefer_domains or []):
        if d in url:
            score += 3
    # Prefer handbook/course pages
    for kw in ["handbook", "courses", "/course/", "outline", "syllabus"]:
        if kw in url:
            score += 2
    # Penalize obvious non-course pages
    for bad in ["/jobs", "/careers", "recruit", "login", "/news/"]:
        if bad in url:
            score -= 4
    return score


def _pick_best_url(code: str, results: list[dict], prefer_domains: list[str] | None = None) -> str | None:
    if not results:
        return None
    # sort by relevance score
    ranked = sorted(results, key=lambda r: _is_relevant_result(code, r, prefer_domains), reverse=True)
    for r in ranked[:5]:
        if _is_relevant_result(code, r, prefer_domains) > 0:
            return r.get("url")
    return ranked[0].get("url") if ranked else None


def _parse_course_page(html: str) -> tuple[str | None, list[str], list[str], list[str]]:
    """Return (name, topics, skills, tools). Heuristic parsing with broader coverage."""
    soup = BeautifulSoup(html or "", "lxml")
    name = None
    if soup.title and soup.title.text:
        name = soup.title.text.strip()
        # clean common noise
        name = re.sub(r"\s*-\s*UNSW.*$", "", name, flags=re.I)
        name = re.sub(r"\bJobs\b.*$", "", name, flags=re.I).strip() or name
    topics: list[str] = []
    skills: list[str] = []
    tools: list[str] = []

    def section_block_items(head_pat: str) -> list[str]:
        out: list[str] = []
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            if not re.search(head_pat, h.get_text(" ", strip=True), re.I):
                continue
            # collect siblings until next heading
            sib = h.next_sibling
            limit = 0
            while sib and limit < 50:
                limit += 1
                nm = (getattr(sib, 'name', '') or '').lower()
                if nm in ["h1", "h2", "h3", "h4"]:
                    break
                if nm in ("ul", "ol"):
                    out.extend([li.get_text(" ", strip=True) for li in sib.find_all("li")])
                elif nm == 'p':
                    txt = sib.get_text(" ", strip=True)
                    if txt and len(txt) > 10:
                        out.extend([seg.strip() for seg in re.split(r"[.;\n]", txt) if len(seg.strip()) > 8])
                sib = sib.next_sibling
        return [s for s in out if len(s) > 2]

    topics = section_block_items(r"topic|outline|syllabus|learning outcome|course content|course overview")
    tools = section_block_items(r"software|tools|technology|environment")

    # derive skills from page text using keywords
    page_text = soup.get_text("\n", strip=True)
    kw = [
        # general CS
        "algorithms", "data structures", "graphs", "trees", "recursion", "dynamic programming", "hashing", "complexity",
        # DB
        "database", "relational", "sql", "normalization", "indexing", "b-trees", "query optimization", "transactions", "concurrency", "er modeling",
        # misc
        "problem solving", "analysis", "design", "implementation",
    ]
    low = (page_text or "").lower()
    for token in kw:
        if token in low and token not in skills:
            skills.append(token.upper() if token in ["sql"] else token.title())

    # derive skills from topics/tools (simple split by commas)
    for s in topics + tools:
        bits = [b.strip() for b in re.split(r"[,;/]", s) if len(b.strip()) > 1]
        for b in bits:
            if b not in skills:
                skills.append(b)
    # cap sizes
    return name, topics[:20], skills[:30], tools[:20]


def _fetch(url: str, timeout: float = 6.0) -> str | None:
    try:
        with httpx.Client(timeout=timeout, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(url)
            if r.status_code < 400:
                return r.text
            return None
    except Exception:
        return None


def _handbook_fallback(code: str) -> tuple[str | None, list[str], list[str], list[str]] | None:
    # Try UNSW handbook directly for recent years and both levels
    years = [2025, 2024, 2023]
    levels = ["undergraduate", "postgraduate"]
    for y in years:
        for lv in levels:
            url = f"https://www.handbook.unsw.edu.au/{lv}/courses/{y}/{code}"
            html = _fetch(url)
            if not html:
                continue
            name, topics, skills, tools = _parse_course_page(html)
            if any([name, topics, skills, tools]):
                return name, topics, skills, tools
    return None


def enrich_courses_from_text(texts: list[str], *, extra_codes: list[str] | None = None) -> tuple[list[Course], list[str]]:
    notes: list[str] = []
    # Collect codes from all texts
    all_text = "\n".join([t for t in texts or [] if t])
    codes = _find_codes(all_text)
    if extra_codes:
        for c in extra_codes:
            cc = (c or "").upper().replace(" ", "").replace("-", "")
            if cc and cc not in codes:
                codes.append(cc)
    if not codes:
        return [], ["no_course_codes"]

    courses: list[Course] = []
    prefer_domains: list[str] = []
    if re.search(r"(?i)unsw|新南威尔士", all_text):
        prefer_domains.extend(["unsw.edu.au", "handbook.unsw.edu.au"])
    # limit number of courses to avoid long waits
    for code in codes[:3]:
        cache_key = f"course:{code}"
        cached = _CACHE.get(cache_key)
        if cached:
            courses.append(cached)
            notes.append("cache_hit:" + code)
            continue

        # web search
        if prefer_domains:
            q = f"{code} syllabus outline handbook site:{prefer_domains[0]} OR site:handbook.unsw.edu.au"
        else:
            q = f"{code} syllabus outline handbook course"
        results = web_search(q, top_k=5, region="AU") or []
        if not results:
            notes.append("course_search_empty:" + code)
            # try handbook fallback directly
            fb = _handbook_fallback(code)
            if fb:
                name, topics, skills, tools = fb
                course = Course(code=code, name=name, topics=topics, skills=skills, tools=tools)
                courses.append(course)
                _CACHE.set(cache_key, course)
                notes.append("course_ok:" + code)
            continue
        # pick first relevant url; if not relevant, try next few
        url = None
        for r in results[:5]:
            if _is_relevant_result(code, r, prefer_domains) > 0:
                url = r.get("url")
                break
        if not url:
            url = results[0].get("url")
        name = None
        topics: list[str] = []
        skills: list[str] = []
        tools: list[str] = []
        ok = False
        if url:
            html = _fetch(url, timeout=6.0)
            if html:
                name, topics, skills, tools = _parse_course_page(html)
                # relevance: page must mention the code or have non-trivial topics/skills
                body_low = BeautifulSoup(html, "lxml").get_text("\n", strip=True).lower()
                code_low = _norm_code(code).lower()
                ok = (code_low in (url or "").lower()) or (code_low in body_low) or bool(topics or skills)
        if not ok:
            fb = _handbook_fallback(code)
            if fb:
                name, topics, skills, tools = fb
                ok = True
        if not ok:
            notes.append("course_parse_empty:" + code)
            continue

        course = Course(code=code, name=name, topics=topics, skills=skills, tools=tools)
        courses.append(course)
        _CACHE.set(cache_key, course)
        notes.append("course_ok:" + code)

    return courses, notes
