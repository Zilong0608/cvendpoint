from __future__ import annotations

from typing import Tuple, List
from fastapi import UploadFile


def parse_resume_docx(file: UploadFile) -> Tuple[dict, str]:
    """Parse a DOCX resume in a preserve-first way, with better heuristics for
    education (school/degree/major/start/end) and experience (company/role/date bullets).
    Returns (profile_dict, plain_text).
    """
    from docx import Document  # type: ignore
    import io
    import re
    import zipfile
    import xml.etree.ElementTree as ET

    # ---------- Helpers ----------
    MONTH_RE = r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"

    def _strip(s: str | None) -> str:
        return (s or "").strip()

    def _is_bullet(s: str) -> bool:
        return bool(re.match(r"^\s*[\-•·\*—–]\s+", s))

    def _clean_bullet(s: str) -> str:
        return re.sub(r"^\s*[\-•·\*—–]\s+", "", s).strip()

    def _is_year_token(s: str) -> bool:
        return bool(re.fullmatch(r"\d{4}", s))

    def _is_present_token(s: str) -> bool:
        return s.lower() in {"present", "current"}

    def _date_range_from_line(s: str) -> tuple[str | None, str | None] | None:
        text = (s or "").strip()
        if not text:
            return None
        # Normalize separators
        norm = re.sub(r"[\u2012\u2013\u2014\u2015]", "-", text)  # dashes -> '-'
        norm = norm.replace("–", "-")
        # 1) YYYY - YYYY/Present
        m = re.search(r"\b(\d{4})\b\s*[-~–—to至到]{1,2}\s*(\d{4}|Present|Current)\b", norm, flags=re.I)
        if m:
            a, b = m.group(1), m.group(2)
            return a, (b if not _is_present_token(b) else "Present")
        # 2) Mon YYYY - Mon YYYY/Present
        m = re.search(rf"\b({MONTH_RE})\s+(\d{{4}})\s*[-~–—]\s*({MONTH_RE})\s+(\d{{4}}|Present|Current)\b", norm, flags=re.I)
        if m:
            start = f"{m.group(1)} {m.group(2)}"
            end = f"{m.group(3)} {m.group(4)}" if not _is_present_token(m.group(4)) else "Present"
            return start, end
        # 3) YYYY (Mon - Mon)
        m = re.search(rf"\b(\d{{4}})\b.*\((?:\s*)({MONTH_RE})\s*[-~–—]\s*({MONTH_RE})(?:\s*)\)", norm, flags=re.I)
        if m:
            year = m.group(1)
            start = f"{m.group(2)} {year}"
            end = f"{m.group(3)} {year}"
            return start, end
        # 4) Tokens split lines like "2025 (Apr" and next line "Jul)" handled elsewhere
        # 5) Lone year token
        m = re.fullmatch(r"\d{4}", norm)
        if m:
            return m.group(0), None
        return None

    def _looks_like_school(s: str) -> bool:
        low = s.lower()
        kw = ["university", "college", "institute", "up education", "high school", "school"]
        return any(k in low for k in kw) and any(ch.isalpha() for ch in s)

    def _looks_like_degree(s: str) -> bool:
        low = s.lower()
        return low.startswith("master of") or low.startswith("bachelor of") or low.startswith("foundation program") or "graduation certificate" in low

    def _split_degree_major(s: str) -> tuple[str | None, str | None]:
        s = s.strip()
        if not s:
            return None, None
        # Extract within parentheses as major (e.g., "(Artificial Intelligence Specialization)")
        m = re.search(r"\((.+?)\)", s)
        major = None
        if m:
            major = m.group(1).strip()
        # Degree is the part before parentheses or the leading phrase
        degree = s.split("(")[0].strip()
        # Normalize common labels
        degree = degree.rstrip(",;.")
        return (degree or None), (major or None)

    def _role_first_pattern(s: str) -> tuple[str | None, str | None]:
        """Match patterns like "Orientation Volunteer, The University of Auckland" -> (company, role).
        Require that the left part contains a role keyword to avoid false positives on skill lines.
        """
        m = re.match(r"^([^,]{2,}?),\s*(.{3,})$", s)
        if not m:
            return None, None
        role, company = m.group(1).strip(), m.group(2).strip()
        # Role keywords heuristic (strong requirement)
        if re.search(r"(?i)\b(intern|engineer|developer|volunteer|assistant|analyst|manager|research|associate|lead|specialist|consultant)\b", role):
            return company, role
        return None, None

    def _company_role_header(s: str) -> tuple[str | None, str | None]:
        """Split "Company - Role" like headers; ensure left is not date-like."""
        # Prefer separators: ' - ', ' — ', ' – ', ' | ', ': '
        parts = re.split(r"\s+[\-—–|:]\s+", s)
        if len(parts) >= 2:
            left, right = parts[0].strip(), parts[1].strip()
            if _date_range_from_line(left):
                return None, None
            if any(ch.isalpha() for ch in left) and any(ch.isalpha() for ch in right):
                return left, right
        return None, None

    # ---------- Read DOCX ----------
    # Always reset file pointer after reading so fallback extractors can re-read
    bio = file.file.read()
    doc = None
    try:
        doc = Document(io.BytesIO(bio))
    except Exception:
        doc = None  # will fall back to XML extraction
    finally:
        try:
            file.file.seek(0)
        except Exception:
            pass

    # Helper: iterate paragraphs in document order, including tables
    def _iter_document_text_lines(document) -> List[str]:
        from docx.oxml.text.paragraph import CT_P  # type: ignore
        from docx.oxml.table import CT_Tbl  # type: ignore
        from docx.table import _Cell, Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore

        def iter_block_items(parent):
            for child in parent.element.body.iterchildren():
                if isinstance(child, CT_P):
                    yield Paragraph(child, parent)
                elif isinstance(child, CT_Tbl):
                    yield Table(child, parent)

        def lines_from_table(tbl: Table) -> List[str]:
            ls: List[str] = []
            for row in tbl.rows:
                for cell in row.cells:
                    # Deduplicate nested tables' paragraphs implicitly
                    for p in cell.paragraphs:
                        t = (p.text or '').strip()
                        if t:
                            ls.append(t)
            return ls

        lines: List[str] = []
        for block in iter_block_items(document):
            if hasattr(block, 'text'):
                t = (block.text or '').strip()
                if t:
                    lines.append(t)
            else:
                # Table
                lines.extend(lines_from_table(block))
        return lines

    def _iter_document_xml_lines(bio_bytes: bytes) -> List[str]:
        try:
            with zipfile.ZipFile(io.BytesIO(bio_bytes)) as z:
                with z.open('word/document.xml') as fxml:
                    xml = fxml.read()
            # Parse and extract all paragraph texts
            ns = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            }
            root = ET.fromstring(xml)
            lines: List[str] = []
            for p in root.findall('.//w:p', ns):
                # concatenate all runs' texts
                texts = [t.text for t in p.findall('.//w:t', ns) if (t.text or '').strip()]
                s = ' '.join(texts).strip()
                if s:
                    lines.append(s)
            return lines
        except Exception:
            return []

    # Try python-docx first; on failure, fall back to XML walk
    all_lines: List[str] = []
    if doc is not None:
        try:
            all_lines = _iter_document_text_lines(doc)
        except Exception:
            all_lines = []
    if not all_lines:
        all_lines = _iter_document_xml_lines(bio)

    # Extract plain text for enrichment (join all lines)
    plain_text = '\n'.join(all_lines)

    sections = {
        'education': ['education'],
        'experience': ['work experience', 'experience'],
        'projects': ['projects'],
        'skills': ['skills'],
        'certifications': ['certifications', 'certificates'],
        'languages': ['languages'],
    }

    def _normalize_header(s: str) -> str:
        # remove bullets, punctuation and collapse spaces
        s = re.sub(r"^[\-•·\*—–\s]+", "", s or "")
        s = s.strip().strip(':：;').lower()
        s = re.sub(r"\s+", " ", s)
        return s

    def which_section(text: str) -> str | None:
        low_full = _normalize_header(text)
        for key, heads in sections.items():
            for h in heads:
                if low_full == h or low_full.startswith(h + ' '):
                    return key
        return None

    current = None
    bucket: dict[str, List[str]] = {k: [] for k in sections.keys()}

    header_re = re.compile(r"^(?P<h>education|work\s+experience|experience|projects|skills|certifications|certificates|languages)\s*[:：]?\s*(?P<rest>.*)$", re.I)
    for t in all_lines:
        tt = (t or '').strip()
        if not tt:
            continue
        m = header_re.match(tt)
        if m:
            h = m.group('h').lower()
            # map alias to canonical key
            for key, heads in sections.items():
                if h in heads:
                    current = key
                    break
            else:
                current = None
            # if header line carries content, push remainder to current bucket
            rest = (m.group('rest') or '').strip()
            if current and rest:
                bucket[current].append(rest)
            continue
        sec = which_section(tt)
        if sec:
            current = sec
            continue
        if current:
            bucket[current].append(tt)

    profile: dict = {
        'education': [],
        'experience': [],
        'projects': [],
        'skills': [],
    }

    # ---------- Education parsing ----------
    edu_lines = bucket['education']
    cur_edu: dict | None = None

    # Merge parentheses broken date like "2025 (Apr" + "Jul)"
    merged_edu: List[str] = []
    i = 0
    while i < len(edu_lines):
        cur = edu_lines[i].strip()
        if i + 1 < len(edu_lines):
            nxt = edu_lines[i + 1].strip()
            if cur.endswith('(') and nxt.endswith(')'):
                merged_edu.append(f"{cur}{nxt}")
                i += 2
                continue
        merged_edu.append(cur)
        i += 1

    moved_from_edu_to_exp: List[dict] = []

    def _is_header_word(s: str, word: str) -> bool:
        return re.sub(r"[:：\s]+$", "", s.lower()) == word

    for line in merged_edu:
        s = line.strip()
        if not s:
            continue
        # Skip stray section headers accidentally captured
        if _is_header_word(s, 'education'):
            continue
        # Ignore notes lines
        if re.match(r"(?i)^(relevant\s+courses|courses|gpa|project|projects)\b", s):
            continue
        # If this line actually looks like an experience (role, company), move it to experience later
        cr = _role_first_pattern(s)
        if cr != (None, None):
            company, role = cr
            moved_from_edu_to_exp.append({'company': company, 'role': role, 'start': None, 'end': None, 'bullets': []})
            continue
        # Date range line
        dr = _date_range_from_line(s)
        if dr and any(dr):
            if cur_edu is None:
                cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}
            start, end = dr
            # Only set if not set yet
            if start and not cur_edu.get('start'):
                cur_edu['start'] = start
            if end and not cur_edu.get('end'):
                cur_edu['end'] = end
            continue
        # Degree line
        if _looks_like_degree(s):
            if cur_edu is None:
                cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}
            deg, maj = _split_degree_major(s)
            if deg and not cur_edu.get('degree'):
                cur_edu['degree'] = deg
            if maj and not cur_edu.get('major'):
                cur_edu['major'] = maj
            continue
        # School line
        if _looks_like_school(s):
            # Flush previous (only if it has a school)
            if cur_edu and cur_edu.get('school'):
                profile['education'].append({k: cur_edu.get(k) for k in ['school', 'degree', 'major', 'start', 'end']})
            # Start new
            cur_edu = {'school': s, 'degree': None, 'major': None, 'start': cur_edu.get('start') if cur_edu else None, 'end': cur_edu.get('end') if cur_edu else None}
            continue
        # Fallback: if looks like degree-ish but not matched, try store to degree
        if cur_edu is None:
            # Do not assume as school; start an empty edu and try to infer later
            cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}
            # If nothing matches, avoid emitting this later

    if cur_edu and cur_edu.get('school'):
        profile['education'].append({k: cur_edu.get(k) for k in ['school', 'degree', 'major', 'start', 'end']})

    # Append any moved experience-like lines found under Education
    for e in moved_from_edu_to_exp:
        profile['experience'].append(e)

    # ---------- Experience parsing ----------
    exp_lines = bucket['experience']

    # Merge lines like "2025 (Apr" + "Jul)"
    merged_exp: List[str] = []
    i = 0
    while i < len(exp_lines):
        cur = exp_lines[i].strip()
        if i + 1 < len(exp_lines):
            nxt = exp_lines[i + 1].strip()
            if cur.endswith('(') and nxt.endswith(')'):
                merged_exp.append(f"{cur}{nxt}")
                i += 2
                continue
        merged_exp.append(cur)
        i += 1

    current_exp = None

    def _flush_exp():
        nonlocal current_exp
        if current_exp:
            # Clean trailing bullets: remove pure year tokens
            clean_bullets = []
            for b in current_exp.get('bullets', []) or []:
                bb = b.strip()
                if _is_year_token(bb):
                    # treat as date if not set
                    if not current_exp.get('start'):
                        current_exp['start'] = bb
                    continue
                clean_bullets.append(bb)
            current_exp['bullets'] = clean_bullets
            profile['experience'].append(current_exp)
            current_exp = None

    for line in merged_exp:
        s = line.strip()
        if not s:
            continue
        # Bullet line
        if _is_bullet(s):
            if current_exp is None:
                current_exp = {'company': '', 'role': '', 'start': None, 'end': None, 'bullets': []}
            b = _clean_bullet(s)
            # Avoid lone year in bullets
            if _is_year_token(b):
                if not current_exp.get('start'):
                    current_exp['start'] = b
                continue
            current_exp.setdefault('bullets', []).append(b)
            continue
        # Date range line
        dr = _date_range_from_line(s)
        if dr and any(dr):
            if current_exp is None:
                current_exp = {'company': '', 'role': '', 'start': None, 'end': None, 'bullets': []}
            start, end = dr
            if start and not current_exp.get('start'):
                current_exp['start'] = start
            if end and not current_exp.get('end'):
                current_exp['end'] = end
            continue
        # Role-first pattern
        comp_role = _role_first_pattern(s)
        if comp_role != (None, None):
            _flush_exp()
            company, role = comp_role
            current_exp = {'company': company, 'role': role, 'start': None, 'end': None, 'bullets': []}
            continue
        # Company - Role header
        comp, role = _company_role_header(s)
        if comp and role:
            _flush_exp()
            current_exp = {'company': comp, 'role': role, 'start': None, 'end': None, 'bullets': []}
            continue
        # Otherwise, heuristics: if looks like short role title and we have company only
        if current_exp and current_exp.get('company') and not current_exp.get('role'):
            # A role line often short and title-case
            if len(s) <= 60 and any(ch.isalpha() for ch in s):
                current_exp['role'] = s
                continue
        # If we have an ongoing experience, treat general lines as bullets rather than starting a new experience
        if current_exp is not None:
            # Many resumes list skills/summary lines without bullet prefix; keep as bullets
            current_exp.setdefault('bullets', []).append(s)
            continue
        # Only if no current experience at all, start a placeholder company
        if any(ch.isalpha() for ch in s) and not _date_range_from_line(s):
            current_exp = {'company': s, 'role': '', 'start': None, 'end': None, 'bullets': []}
            continue

    _flush_exp()

    # ---------- Projects (keep simple, but merge parentheses pairs) ----------
    proj_lines = bucket['projects']
    merged: List[str] = []
    i = 0
    while i < len(proj_lines):
        cur = proj_lines[i].strip()
        if i + 1 < len(proj_lines):
            nxt = proj_lines[i + 1].strip()
            # Merge if current line contains an opening '(' without a closing ')', and next ends with ')'
            if ('(' in cur and ')' not in cur) and nxt.endswith(')'):
                merged.append(f"{cur}{'' if cur.endswith('(') else ' '}{nxt}")
                i += 2
                continue
            # Original simple pair merge
            if cur.endswith('(') and nxt.endswith(')'):
                merged.append(f"{cur}{nxt}")
                i += 2
                continue
        merged.append(cur)
        i += 1
    if merged:
        block: List[str] = []
        for ln in merged:
            if not ln:
                continue
            block.append(_clean_bullet(ln) if _is_bullet(ln) else ln)
        profile['projects'].append({'company': 'Projects', 'role': None, 'bullets': block})

    # ---------- Skills (raw tokens by commas/semicolons) ----------
    skills_raw = ', '.join(bucket['skills'])
    skills = []
    for tok in re.split(r"[,;]", skills_raw):
        s = tok.strip()
        if s:
            skills.append(s)
    profile['skills'] = skills

    return profile, plain_text


def parse_resume_text_preserve(text: str) -> Tuple[dict, str]:
    """Preserve-first parsing from plain text (PDF/HTML/other) using the same
    rules as DOCX path: section detection, education/experience/projects/skills
    extraction, date range handling, and bullet normalization.
    """
    # Reuse the same inner logic by feeding 'all_lines'
    lines = [ln.strip() for ln in (text or '').splitlines() if (ln or '').strip()]
    # Build a faux UploadFile-independent flow by calling into the same code paths
    # We mirror the later part of parse_resume_docx after 'all_lines' is prepared.
    import re

    def _normalize_header(s: str) -> str:
        s = re.sub(r"^[\-•·\*—–\s]+", "", s or "")
        s = s.strip().strip(':：;').lower()
        s = re.sub(r"\s+", " ", s)
        return s

    sections = {
        'education': ['education'],
        'experience': ['work experience', 'experience'],
        'projects': ['projects'],
        'skills': ['skills'],
        'certifications': ['certifications', 'certificates'],
        'languages': ['languages'],
    }

    def which_section(text: str) -> str | None:
        low = _normalize_header(text)
        for key, heads in sections.items():
            for h in heads:
                if low == h:
                    return key
        return None

    # We will reuse the same parsing helpers by importing this module itself
    # and calling the inner logic through a minimal shim: create a fake 'doc'
    # by injecting lines into the same variables.

    # We replicate the bucket/profile building logic inline to avoid circular refs.
    current = None
    bucket: dict[str, List[str]] = {k: [] for k in sections.keys()}
    for tt in lines:
        sec = which_section(tt)
        if sec:
            current = sec
            continue
        if current:
            bucket[current].append(tt)

    # Reuse the same lower blocks by copying minimal helper subset
    MONTH_RE = r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"

    def _is_bullet(s: str) -> bool:
        return bool(re.match(r"^\s*[\-•·\*—–]\s+", s))

    def _clean_bullet(s: str) -> str:
        return re.sub(r"^\s*[\-•·\*—–]\s+", "", s).strip()

    def _is_year_token(s: str) -> bool:
        return bool(re.fullmatch(r"\d{4}", s))

    def _is_present_token(s: str) -> bool:
        return s.lower() in {"present", "current"}

    def _date_range_from_line(s: str) -> tuple[str | None, str | None] | None:
        text = (s or "").strip()
        if not text:
            return None
        norm = re.sub(r"[\u2012\u2013\u2014\u2015]", "-", text)
        norm = norm.replace("–", "-")
        m = re.search(r"\b(\d{4})\b\s*[-~–—to至到]{1,2}\s*(\d{4}|Present|Current)\b", norm, flags=re.I)
        if m:
            a, b = m.group(1), m.group(2)
            return a, (b if not _is_present_token(b) else "Present")
        m = re.search(rf"\b({MONTH_RE})\s+(\d{{4}})\s*[-~–—]\s*({MONTH_RE})\s+(\d{{4}}|Present|Current)\b", norm, flags=re.I)
        if m:
            start = f"{m.group(1)} {m.group(2)}"
            end = f"{m.group(3)} {m.group(4)}" if not _is_present_token(m.group(4)) else "Present"
            return start, end
        m = re.search(rf"\b(\d{{4}})\b.*\((?:\s*)({MONTH_RE})\s*[-~–—]\s*({MONTH_RE})(?:\s*)\)", norm, flags=re.I)
        if m:
            year = m.group(1)
            start = f"{m.group(2)} {year}"
            end = f"{m.group(3)} {year}"
            return start, end
        m = re.fullmatch(r"\d{4}", norm)
        if m:
            return m.group(0), None
        return None

    def _looks_like_school(s: str) -> bool:
        low = s.lower()
        kw = ["university", "college", "institute", "up education", "high school", "school"]
        return any(k in low for k in kw) and any(ch.isalpha() for ch in s)

    def _looks_like_degree(s: str) -> bool:
        low = s.lower()
        return low.startswith("master of") or low.startswith("bachelor of") or low.startswith("foundation program") or "graduation certificate" in low

    def _split_degree_major(s: str) -> tuple[str | None, str | None]:
        s = s.strip()
        if not s:
            return None, None
        m = re.search(r"\((.+?)\)", s)
        major = None
        if m:
            major = m.group(1).strip()
        degree = s.split("(")[0].strip()
        degree = degree.rstrip(",;.")
        return (degree or None), (major or None)

    def _role_first_pattern(s: str) -> tuple[str | None, str | None]:
        m = re.match(r"^([^,]{2,}?),\s*(.{3,})$", s)
        if not m:
            return None, None
        role, company = m.group(1).strip(), m.group(2).strip()
        if re.search(r"(?i)\b(intern|engineer|developer|volunteer|assistant|analyst|manager|research|associate|lead|specialist|consultant)\b", role):
            return company, role
        return None, None

    def _company_role_header(s: str) -> tuple[str | None, str | None]:
        parts = re.split(r"\s+[\-—–|:]\s+", s)
        if len(parts) >= 2:
            left, right = parts[0].strip(), parts[1].strip()
            if _date_range_from_line(left):
                return None, None
            if any(ch.isalpha() for ch in left) and any(ch.isalpha() for ch in right):
                return left, right
        return None, None

    profile: dict = {
        'education': [],
        'experience': [],
        'projects': [],
        'skills': [],
    }

    # Education
    edu_lines = bucket['education']
    cur_edu: dict | None = None
    moved_from_edu_to_exp: List[dict] = []

    def _is_header_word(s: str, word: str) -> bool:
        return re.sub(r"[:：\s]+$", "", s.lower()) == word

    # Merge parenthesis pairs across lines
    merged_edu: List[str] = []
    i = 0
    while i < len(edu_lines):
        cur = edu_lines[i].strip()
        if i + 1 < len(edu_lines):
            nxt = edu_lines[i + 1].strip()
            if ('(' in cur and ')' not in cur) and nxt.endswith(')'):
                merged_edu.append(f"{cur} {nxt}")
                i += 2
                continue
            if cur.endswith('(') and nxt.endswith(')'):
                merged_edu.append(f"{cur}{nxt}")
                i += 2
                continue
        merged_edu.append(cur)
        i += 1

    for s in merged_edu:
        if not s:
            continue
        if _is_header_word(s, 'education'):
            continue
        if re.match(r"(?i)^(relevant\s+courses|courses|gpa|project|projects)\b", s):
            continue
        cr = _role_first_pattern(s)
        if cr != (None, None):
            company, role = cr
            moved_from_edu_to_exp.append({'company': company, 'role': role, 'start': None, 'end': None, 'bullets': []})
            continue
        dr = _date_range_from_line(s)
        if dr and any(dr):
            if cur_edu is None:
                cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}
            start, end = dr
            if start and not cur_edu.get('start'):
                cur_edu['start'] = start
            if end and not cur_edu.get('end'):
                cur_edu['end'] = end
            continue
        if _looks_like_degree(s):
            if cur_edu is None:
                cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}
            deg, maj = _split_degree_major(s)
            if deg and not cur_edu.get('degree'):
                cur_edu['degree'] = deg
            if maj and not cur_edu.get('major'):
                cur_edu['major'] = maj
            continue
        if _looks_like_school(s):
            if cur_edu and cur_edu.get('school'):
                profile['education'].append({k: cur_edu.get(k) for k in ['school', 'degree', 'major', 'start', 'end']})
            cur_edu = {'school': s, 'degree': None, 'major': None, 'start': cur_edu.get('start') if cur_edu else None, 'end': cur_edu.get('end') if cur_edu else None}
            continue
        if cur_edu is None:
            cur_edu = {'school': None, 'degree': None, 'major': None, 'start': None, 'end': None}

    if cur_edu and cur_edu.get('school'):
        profile['education'].append({k: cur_edu.get(k) for k in ['school', 'degree', 'major', 'start', 'end']})
    for e in moved_from_edu_to_exp:
        profile['experience'].append(e)

    # Experience
    exp_lines = bucket['experience']
    merged_exp: List[str] = []
    i = 0
    while i < len(exp_lines):
        cur = exp_lines[i].strip()
        if i + 1 < len(exp_lines):
            nxt = exp_lines[i + 1].strip()
            if ('(' in cur and ')' not in cur) and nxt.endswith(')'):
                merged_exp.append(f"{cur} {nxt}")
                i += 2
                continue
            if cur.endswith('(') and nxt.endswith(')'):
                merged_exp.append(f"{cur}{nxt}")
                i += 2
                continue
        merged_exp.append(cur)
        i += 1

    current_exp = None

    def _flush_exp():
        nonlocal current_exp
        if current_exp:
            clean_bullets = []
            for b in current_exp.get('bullets', []) or []:
                bb = b.strip()
                if _is_year_token(bb):
                    if not current_exp.get('start'):
                        current_exp['start'] = bb
                    continue
                clean_bullets.append(bb)
            current_exp['bullets'] = clean_bullets
            profile['experience'].append(current_exp)
            current_exp = None

    for s in merged_exp:
        if not s:
            continue
        if _is_bullet(s):
            if current_exp is None:
                current_exp = {'company': '', 'role': '', 'start': None, 'end': None, 'bullets': []}
            b = _clean_bullet(s)
            if _is_year_token(b):
                if not current_exp.get('start'):
                    current_exp['start'] = b
                continue
            current_exp.setdefault('bullets', []).append(b)
            continue
        dr = _date_range_from_line(s)
        if dr and any(dr):
            if current_exp is None:
                current_exp = {'company': '', 'role': '', 'start': None, 'end': None, 'bullets': []}
            start, end = dr
            if start and not current_exp.get('start'):
                current_exp['start'] = start
            if end and not current_exp.get('end'):
                current_exp['end'] = end
            continue
        comp_role = _role_first_pattern(s)
        if comp_role != (None, None):
            _flush_exp()
            company, role = comp_role
            current_exp = {'company': company, 'role': role, 'start': None, 'end': None, 'bullets': []}
            continue
        comp, role = _company_role_header(s)
        if comp and role:
            _flush_exp()
            current_exp = {'company': comp, 'role': role, 'start': None, 'end': None, 'bullets': []}
            continue
        if current_exp is not None:
            current_exp.setdefault('bullets', []).append(s)
            continue
        if any(ch.isalpha() for ch in s) and not _date_range_from_line(s):
            current_exp = {'company': s, 'role': '', 'start': None, 'end': None, 'bullets': []}
            continue
    _flush_exp()

    # Projects
    proj_lines = bucket['projects']
    merged: List[str] = []
    i = 0
    while i < len(proj_lines):
        cur = proj_lines[i].strip()
        if i + 1 < len(proj_lines):
            nxt = proj_lines[i + 1].strip()
            if ('(' in cur and ')' not in cur) and nxt.endswith(')'):
                merged.append(f"{cur} {nxt}")
                i += 2
                continue
            if cur.endswith('(') and nxt.endswith(')'):
                merged.append(f"{cur}{nxt}")
                i += 2
                continue
        merged.append(cur)
        i += 1
    if merged:
        block: List[str] = []
        for ln in merged:
            if not ln:
                continue
            block.append(_clean_bullet(ln) if _is_bullet(ln) else ln)
        profile['projects'].append({'company': 'Projects', 'role': None, 'bullets': block, 'start': None, 'end': None})

    # Skills
    skills_raw = ', '.join(bucket['skills'])
    skills = []
    for tok in re.split(r"[,;]", skills_raw):
        s = tok.strip()
        if s:
            skills.append(s)
    profile['skills'] = skills

    return profile, '\n'.join(lines)
