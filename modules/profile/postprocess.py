from __future__ import annotations

import re
from typing import List

from .schemas import Profile, Education, Experience


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _clean_contact(contact: str | None, base_text: str) -> str | None:
    if not (contact and contact.strip()):
        m = EMAIL_RE.search(base_text or "")
        return m.group(0) if m else None
    s = contact.strip()
    m = EMAIL_RE.search(s)
    return m.group(0) if m else s


def _clean_location(loc: str | None, base_text: str) -> str | None:
    s = (loc or "").strip()
    s = re.sub(r"^(?i)address\s*:\s*", "", s)
    return s or None


def normalize_contact_location(profile: Profile, *, base_text: str = "") -> None:
    profile.contact = _clean_contact(profile.contact, base_text)
    profile.location = _clean_location(profile.location, base_text)


def _is_title_only(s: str) -> bool:
    return s.strip().lower() in {"education", "work experience", "experience", "projects"}


def _norm_school_name(name: str) -> str:
    s = name.strip()
    if re.search(r"(?i)unsw|new south wales", s):
        return "University of New South Wales"
    return s


def normalize_education(profile: Profile, *, base_text: str = "") -> None:
    edus: List[Education] = []
    pending_volunteer: List[str] = []
    # Extract degree/major lines
    for e in profile.education or []:
        school = (e.school or "").strip()
        if not school or _is_title_only(school):
            continue
        if re.search(r"(?i)volunteer", school):
            pending_volunteer.append(school)
            continue
        deg = e.degree
        maj = e.major
        # If school line actually contains degree text
        m = re.match(r"(?i)(Master|Bachelor)[^()]*", school)
        if m and not deg:
            deg = school.strip()
            pm = re.search(r"\(([^)]+)\)", school)
            if pm:
                maj = Maj = pm.group(1)
            # try to attach to UNSW if present
            attached = False
            for x in edus:
                if re.search(r"(?i)unsw|new south wales", x.school or "") and not x.degree:
                    x.degree = deg
                    if maj and not x.major:
                        x.major = maj
                    attached = True
                    break
            if not attached:
                edus.append(Education(school="University of New South Wales" if re.search(r"(?i)unsw|new south wales", base_text) else "", degree=deg, major=maj, start=e.start, end=e.end))
            continue
        # Normal path
        school = _norm_school_name(school)
        edus.append(Education(school=school, degree=deg, major=maj, start=e.start, end=e.end))

    # De-dup by (school, degree)
    seen = set()
    out: List[Education] = []
    for e in edus:
        key = (e.school or "", e.degree or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    profile.education = out

    # Move volunteer lines into experience bullets if any actual experience exists
    if pending_volunteer and (profile.experience or []):
        target = profile.experience[0]
        target.bullets = (target.bullets or []) + pending_volunteer


def _looks_like_company(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", s)) and not bool(re.search(r"\(|\)|,\s*[A-Za-z]", s))


def _merge_broken_bullets(bullets: List[str]) -> List[str]:
    if not bullets:
        return []
    out: List[str] = []
    i = 0
    while i < len(bullets):
        cur = (bullets[i] or "").strip()
        if i + 1 < len(bullets):
            nxt = (bullets[i + 1] or "").strip()
            # Merge if looks like broken parenthesis continuation
            if (cur.endswith("(") and nxt.endswith(")")) or (not re.search(r"[\.!?)]$", cur) and nxt and nxt[0].islower()):
                cur = (cur + " " + nxt).strip()
                i += 2
                out.append(cur)
                continue
        out.append(cur)
        i += 1
    return out


def normalize_experience_projects(profile: Profile) -> None:
    # Do not modify existing experiences if present; only normalize project bullets.
    # Keep experiences order/content exactly as parsed.
    # Merge broken bullets in projects only.
    projs: List[Experience] = []
    for p in profile.projects or []:
        bs = _merge_broken_bullets(p.bullets or [])
        projs.append(Experience(company=p.company, role=p.role, start=p.start, end=p.end, bullets=bs))
    profile.projects = projs


def canonicalize_skill_list(skills: List[str]) -> List[str]:
    if not skills:
        return []
    out: List[str] = []
    pres = {s.lower(): s for s in skills}

    def add(s: str):
        if s.lower() not in (x.lower() for x in out):
            out.append(s)

    # Fix common casing
    casing = {"javascript": "JavaScript", "tensorflow": "TensorFlow", "fastapi": "FastAPI", "postgres": "PostgreSQL", "pytorch": "PyTorch"}
    temp = []
    for s in skills:
        low = s.lower().strip()
        if low in casing:
            temp.append(casing[low])
        else:
            temp.append(s)

    pres = {s.lower(): s for s in temp}

    def has(k: str) -> bool:
        return k in pres

    # Combine phrases if atoms present
    if has("algorithms") and has("data structures"):
        add("Algorithms & Data Structures"); pres.pop("algorithms", None); pres.pop("data structures", None)
    if has("algorithms") and has("complexity"):
        add("Algorithmic Complexity"); pres.pop("algorithms", None); pres.pop("complexity", None)
    if has("graphs") and has("trees"):
        add("Graph/Tree Algorithms"); pres.pop("graphs", None); pres.pop("trees", None)
    if has("python") and has("numpy"):
        add("Python + NumPy"); pres.pop("python", None); pres.pop("numpy", None)
    # AI phrases
    if has("search") and has("planning"):
        add("Search & Planning"); pres.pop("search", None); pres.pop("planning", None)
    if has("logic") and has("inference"):
        add("Logic & Inference"); pres.pop("logic", None); pres.pop("inference", None)
    if has("knowledge representation"):
        add("Knowledge Representation"); pres.pop("knowledge representation", None)
    if has("artificial intelligence"):
        add("Artificial Intelligence"); pres.pop("artificial intelligence", None)

    # Keep key singles
    for key, title in [("dynamic programming", "Dynamic Programming"), ("recursion", "Recursion"), ("machine learning", "Machine Learning"), ("sql", "SQL"), ("nlp", "NLP"), ("c++", "C++")]:
        if has(key):
            add(title); pres.pop(key, None)

    # Append remaining with title case
    for k, v in list(pres.items()):
        add(v if v.isupper() else v.title())

    # Limit and return
    return out
