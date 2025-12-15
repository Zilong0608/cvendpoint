from __future__ import annotations

import re
from typing import Tuple, List, Dict, Any


def parse_text_preserve(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse resume plain text into a preserve-first profile dict.

    - Keeps original bullets (no rewriting)
    - Recognizes section headers (Education/Experience/Projects/Skills)
    - Maps degree/major, date ranges, company/role
    - Merges bracket-split lines like "(Python" + "TensorFlow)"
    """
    raw_lines = [ln.strip() for ln in (text or "").splitlines() if (ln or "").strip()]
    lines: List[str] = []
    for ln in raw_lines:
        normalized = re.sub(r"[\ufffd\uF0B7\u00B7]+", "•", ln)
        if normalized.count("•") >= 2 and normalized.strip().startswith("•"):
            parts = [p.strip() for p in re.split(r"\s*•\s+", normalized) if p.strip()]
            lines.extend([f"• {p}" for p in parts])
        else:
            lines.append(normalized)
    if not lines:
        return {}, ""

    def norm_header(s: str) -> str:
        s2 = re.sub(r"^[\-•·\*—–\s]+", "", s or "").strip().strip(':：;').lower()
        s2 = re.sub(r"\s+", " ", s2)
        return s2

    hdr_alias = {
        "education": {"education"},
        "experience": {"experience", "work experience", "employment history"},
        "projects": {"projects", "project"},
        "skills": {"skills", "skill"},
        "languages": {"languages", "language"},
        "certifications": {"certifications", "certificates"},
    }

    def which_section(s: str) -> str | None:
        v = norm_header(s)
        for key, al in hdr_alias.items():
            if v == key or v in al or v.startswith(key + " "):
                return key
        return None

    # Buckets by section + preamble
    bucket: Dict[str, List[str]] = {k: [] for k in hdr_alias}
    preamble: List[str] = []
    current: str | None = None
    header_re = re.compile(r"^(?P<h>education|experience|work\s+experience|employment\s+history|projects|skills|languages|certifications|certificates)\s*[:：]?\s*(?P<rest>.*)$", re.I)
    for ln in lines:
        m = header_re.match(ln)
        if m:
            h = m.group('h').lower().replace('work experience', 'experience')
            current = h if h in bucket else which_section(h)
            rest = (m.group('rest') or '').strip()
            if current and rest:
                bucket[current].append(rest)
            continue
        sec = which_section(ln)
        if sec:
            current = sec
            continue
        if current:
            bucket[current].append(ln)
        else:
            preamble.append(ln)

    # Helpers
    MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"
    EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{6,}")

    BULLET_LEAD = re.compile(r"^\s*[\-•·\*—–\u2022\u2023\u25AA\u25CF\u25C6\u00B7]+\s+")

    def is_bullet(s: str) -> bool:
        return bool(BULLET_LEAD.match(s))

    def clean_bullet(s: str) -> str:
        return BULLET_LEAD.sub("", s, count=1).strip()

    def is_year_token(s: str) -> bool:
        return bool(re.fullmatch(r"\d{4}", s))

    def is_present_token(s: str) -> bool:
        return (s or "").strip().lower() in {"present", "current"}

    def date_range_from_line(s: str) -> tuple[str | None, str | None] | None:
        t = (s or "").strip()
        if not t:
            return None
        t = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212–—−]", "-", t)
        m = re.search(r"\b(\d{4})\b\s*[-~–—to至到]{1,2}\s*(\d{4}|Present|Current)\b", t, flags=re.I)
        if m:
            a, b = m.group(1), m.group(2)
            return a, (b if not is_present_token(b) else "Present")
        m = re.search(rf"\b({MONTH_RE})\s+(\d{{4}})\s*[-~–—]\s*({MONTH_RE})\s+(\d{{4}}|Present|Current)\b", t, flags=re.I)
        if m:
            start = f"{m.group(1)} {m.group(2)}"
            end = f"{m.group(3)} {m.group(4)}" if not is_present_token(m.group(4)) else "Present"
            return start, end
        m = re.search(rf"\b(\d{{4}})\b.*\((?:\s*)({MONTH_RE})\s*[-~–—]\s*({MONTH_RE})(?:\s*)\)", t, flags=re.I)
        if m:
            year = m.group(1)
            return f"{m.group(2)} {year}", f"{m.group(3)} {year}"
        if re.fullmatch(r"\d{4}", t):
            return t, None
        return None

    def looks_like_school(s: str) -> bool:
        low = s.lower()
        return any(k in low for k in ["university", "college", "institute", "up education", "high school", "school"]) and any(ch.isalpha() for ch in s)

    def looks_like_degree(s: str) -> bool:
        low = s.lower()
        return low.startswith("master of") or low.startswith("bachelor of") or low.startswith("foundation program") or "graduation certificate" in low

    def split_degree_major(s: str) -> tuple[str | None, str | None]:
        s = (s or '').strip()
        m = re.search(r"\((.+?)\)", s)
        major = m.group(1).strip() if m else None
        degree = s.split("(")[0].strip().rstrip(",;.")
        return (degree or None), (major or None)

    def dedup_list(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for item in items:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out

    # Basic personal info extraction from preamble
    name: str | None = None
    location: str | None = None
    contact_parts: List[str] = []
    contact_seen: set[str] = set()
    summary_lines: List[str] = []

    NAME_STOP_WORDS = {"professional summary", "summary", "profile", "career objective"}

    def maybe_add_contact(part: str, key: str | None = None):
        part_clean = re.sub(r"\s+", " ", (part or "").strip().strip('|•·-'))
        if not part_clean:
            return
        # avoid lone years or short tokens like "2023"
        if part_clean.isdigit() and len(part_clean) <= 4:
            return
        k = key or part_clean.lower()
        if k in contact_seen:
            return
        contact_seen.add(k)
        contact_parts.append(part_clean)

    for raw in preamble:
        text_line = raw.strip()
        if not text_line:
            continue
        # Split by common separators to inspect pieces
        segments = [seg.strip() for seg in re.split(r"[|•·]", text_line) if seg.strip()]
        if not segments:
            segments = [text_line]
        consumed_line = False
        for seg in segments:
            if not name:
                # Candidate name: alphabetic words, short, no @, skip known headers
                if EMAIL_RE.search(seg):
                    continue
                seg_simple = re.sub(r"\s+", " ", seg)
                seg_norm = seg_simple.strip()
                seg_lower = seg_norm.lower()
                if seg_lower not in NAME_STOP_WORDS and re.fullmatch(r"[A-Za-z][A-Za-z0-9\s\.\-\(\)]{1,80}", seg_norm):
                    name = seg_norm
                    consumed_line = True
                    continue
            matched_contact = False
            email_match = EMAIL_RE.search(seg)
            if email_match:
                maybe_add_contact(email_match.group(0))
                matched_contact = True
            phone_match = PHONE_RE.search(seg)
            if phone_match:
                digits = re.sub(r"\D", "", phone_match.group(0))
                maybe_add_contact(phone_match.group(0), key=digits or None)
                matched_contact = True
            if matched_contact:
                consumed_line = True
                continue
            if not location:
                if re.search(r"(?i)\b(street|st\.|road|rd\.|address|suite|floor|unit|apt|avenue|ave\.)\b", seg) or re.match(r"^\s*\d{1,4}\s+[A-Za-z]", seg):
                    cleaned = seg.replace("Address:", "").strip()
                    location = cleaned
                    consumed_line = True
                    continue
            # capture remaining meaningful pieces (e.g., address line)
            # intentionally skip generic digit-only lines to avoid misclassifying summary sentences
        if not consumed_line and norm_header(text_line) not in NAME_STOP_WORDS:
            summary_lines.append(text_line)

    # Education
    edu: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None

    def ensure_current_edu():
        nonlocal cur
        if cur is None:
            cur = {"school": None, "degree": None, "major": None, "start": None, "end": None}
        return cur

    def commit_current_edu():
        nonlocal cur
        if cur and (cur.get('school') or cur.get('degree') or cur.get('major') or cur.get('start') or cur.get('end')):
            edu.append(cur)
        cur = None
    # merge bracket pairs across lines in education bucket
    edulines = []
    i = 0
    bl = bucket.get('education') or []
    while i < len(bl):
        curline = bl[i].strip()
        if i + 1 < len(bl):
            nxt = bl[i+1].strip()
            if ('(' in curline and ')' not in curline) and nxt.endswith(')'):
                edulines.append(f"{curline} {nxt}")
                i += 2
                continue
        edulines.append(curline)
        i += 1

    def is_header_line(s: str) -> bool:
        return norm_header(s) in {"education", "experience", "projects", "skills", "languages", "certifications"}

    moved_to_exp: List[Dict[str, Any]] = []
    for ln in edulines:
        if not ln or is_header_line(ln):
            continue
        # Degree / Major
        if looks_like_degree(ln):
            cur = ensure_current_edu()
            deg, maj = split_degree_major(ln)
            if deg and not cur.get('degree'):
                cur['degree'] = deg
            if maj and not cur.get('major'):
                cur['major'] = maj
            continue
        # Date
        dr = date_range_from_line(ln)
        if dr and any(dr):
            if cur and cur.get('school'):
                commit_current_edu()
            cur = ensure_current_edu()
            a, b = dr
            if a and not cur.get('start'):
                cur['start'] = a
            if b and not cur.get('end'):
                cur['end'] = b
            continue
        # Role-first lines incorrectly placed under education → move to experience
        m = re.match(r"^([^,]{2,}?),\s*(.{3,})$", ln)
        if m and re.search(r"(?i)\b(intern|engineer|developer|volunteer|assistant|analyst|manager|research|associate|lead|specialist|consultant)\b", m.group(1)):
            moved_to_exp.append({"company": m.group(2).strip(), "role": m.group(1).strip(), "start": None, "end": None, "bullets": []})
            continue
        # School line
        if looks_like_school(ln):
            if cur and cur.get('school'):
                commit_current_edu()
            cur = ensure_current_edu()
            cur['school'] = ln
            continue
    commit_current_edu()

    # Experience
    exp: List[Dict[str, Any]] = []
    curx: Dict[str, Any] | None = None

    def commit_current_exp():
        nonlocal curx
        if curx and any(
            [
                (curx.get('company') or '').strip(),
                (curx.get('role') or '').strip(),
                curx.get('start'),
                curx.get('end'),
                curx.get('bullets'),
            ]
        ):
            exp.append(curx)
        curx = None

    for ln in (bucket.get('experience') or []):
        if not ln or is_header_line(ln):
            continue
        if is_bullet(ln):
            if curx is None:
                curx = {"company": "", "role": "", "start": None, "end": None, "bullets": []}
            b = clean_bullet(ln)
            if is_year_token(b):
                if not curx.get('start'):
                    curx['start'] = b
            else:
                curx.setdefault('bullets', []).append(b)
            continue
        dr = date_range_from_line(ln)
        if dr and any(dr):
            if curx is None:
                curx = {"company": "", "role": "", "start": None, "end": None, "bullets": []}
            a, b = dr
            if a and not curx.get('start'):
                curx['start'] = a
            if b and not curx.get('end'):
                curx['end'] = b
            continue
        # Role, Company
        m = re.match(r"^([^,]{2,}?),\s*(.{3,})$", ln)
        if m and re.search(r"(?i)\b(intern|engineer|developer|volunteer|assistant|analyst|manager|research|associate|lead|specialist|consultant)\b", m.group(1)):
            if curx and not ((curx.get('company') or '').strip() or (curx.get('role') or '').strip()):
                curx['company'] = m.group(2).strip()
                curx['role'] = m.group(1).strip()
                continue
            commit_current_exp()
            curx = {"company": m.group(2).strip(), "role": m.group(1).strip(), "start": None, "end": None, "bullets": []}
            continue
        # Company - Role
        parts = re.split(r"\s+[\-—–|:]\s+", ln)
        if len(parts) >= 2 and any(ch.isalpha() for ch in parts[0]) and any(ch.isalpha() for ch in parts[1]):
            if curx and not ((curx.get('company') or '').strip() or (curx.get('role') or '').strip()):
                curx['company'] = parts[0].strip()
                curx['role'] = parts[1].strip()
                continue
            commit_current_exp()
            curx = {"company": parts[0].strip(), "role": parts[1].strip(), "start": None, "end": None, "bullets": []}
            continue
        # Fallback: attach as bullet if we have a current exp
        if curx is not None:
            curx.setdefault('bullets', []).append(ln)
            continue
        # Else start a placeholder experience
        if any(ch.isalpha() for ch in ln):
            curx = {"company": ln, "role": "", "start": None, "end": None, "bullets": []}
    commit_current_exp()

    # Projects
    proj_lines = bucket.get('projects') or []
    merged: List[str] = []
    i = 0
    while i < len(proj_lines):
        curp = proj_lines[i].strip()
        if i + 1 < len(proj_lines):
            nxt = proj_lines[i+1].strip()
            if ('(' in curp and ')' not in curp) and nxt.endswith(')'):
                merged.append(f"{curp} {nxt}")
                i += 2
                continue
        merged.append(curp)
        i += 1
    projects: List[Dict[str, Any]] = []
    edu_from_projects: List[Dict[str, Any]] = []
    pending_edu: Dict[str, Any] | None = None

    def ensure_pending_edu():
        nonlocal pending_edu
        if pending_edu is None:
            pending_edu = {"school": None, "degree": None, "major": None, "start": None, "end": None}

    def flush_pending_edu():
        nonlocal pending_edu
        if pending_edu and pending_edu.get('school'):
            edu_from_projects.append(pending_edu)
        pending_edu = None

    if merged:
        block: List[str] = []
        for ln in merged:
            if not ln:
                continue
            text_line = clean_bullet(ln) if is_bullet(ln) else ln
            dr = date_range_from_line(text_line)
            if dr and any(dr):
                if pending_edu and pending_edu.get('school') and any(
                    pending_edu.get(k) for k in ('start', 'end', 'degree', 'major')
                ):
                    flush_pending_edu()
                    ensure_pending_edu()
                ensure_pending_edu()
                a, b = dr
                if a and not pending_edu.get('start'):
                    pending_edu['start'] = a
                if b and not pending_edu.get('end'):
                    pending_edu['end'] = b
                continue
            if looks_like_degree(text_line):
                ensure_pending_edu()
                deg, maj = split_degree_major(text_line)
                if deg and not pending_edu.get('degree'):
                    pending_edu['degree'] = deg
                if maj and not pending_edu.get('major'):
                    pending_edu['major'] = maj
                continue
            if looks_like_school(text_line):
                ensure_pending_edu()
                if pending_edu.get('school'):
                    flush_pending_edu()
                    ensure_pending_edu()
                pending_edu['school'] = text_line
                continue
            if re.search(r"(?i)\bGPA\b", text_line):
                # GPA line often belongs to education; skip for now
                ensure_pending_edu()
                continue
            block.append(text_line)
        flush_pending_edu()
        if block:
            projects.append({"company": "Projects", "role": None, "bullets": block})

    # Skills extraction
    raw_skills = []
    for ln in bucket.get('skills') or []:
        text_line = clean_bullet(ln) if is_bullet(ln) else ln.strip()
        if not text_line:
            continue
        # skip header residue like '& Certifications'
        if re.fullmatch(r"&?\s*certifications?", text_line, flags=re.I):
            continue
        parts = [p.strip() for p in re.split(r"[;,]", text_line) if p.strip()]
        if parts:
            i = 0
            while i < len(parts):
                part = parts[i]
                paren_balance = part.count("(") - part.count(")")
                while paren_balance > 0 and i + 1 < len(parts):
                    i += 1
                    part = f"{part}, {parts[i]}"
                    paren_balance += parts[i].count("(") - parts[i].count(")")
                raw_skills.append(part)
                i += 1
        else:
            raw_skills.append(text_line)
    norm_skills: List[str] = []
    for s in raw_skills:
        t = s.strip()
        if not t:
            continue
        if t.lower().startswith("and "):
            t = t[4:].strip()
        if t and t[0].islower():
            t = t[0].upper() + t[1:]
        norm_skills.append(t)
    skills = dedup_list(norm_skills)

    # Languages extraction
    languages: List[str] = []
    for ln in bucket.get('languages') or []:
        text_line = clean_bullet(ln) if is_bullet(ln) else ln.strip()
        if not text_line:
            continue
        parts = [p.strip() for p in re.split(r"[;,]", text_line) if p.strip()]
        if parts:
            languages.extend(parts)
        else:
            languages.append(text_line)
    languages = dedup_list(languages)

    contact_str = " | ".join(dedup_list(contact_parts)) if contact_parts else None

    profile = {
        "name": name,
        "contact": contact_str,
        "location": location,
        "summary": " ".join(summary_lines).strip() or None,
        "education": edu + edu_from_projects,
        "experience": exp + moved_to_exp,
        "projects": projects,
        "skills": skills,
        "languages": languages,
    }
    return profile, text or ""

