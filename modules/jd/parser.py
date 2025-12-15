from bs4 import BeautifulSoup
import re
import json
from typing import Any, Tuple
from .schemas import ParsedJD


HEADINGS_RESP = re.compile(r"responsibilit|what you'll do|what you will do|key duties|about the role", re.I)
HEADINGS_REQ = re.compile(r"requirement|qualification|about you|skills|experience|what you bring", re.I)

RESP_VERBS = re.compile(r"\b(design|develop|build|implement|maintain|deliver|own|lead|optimi[sz]e|deploy|monitor|troubleshoot)\b", re.I)
REQ_TOKENS = re.compile(r"\b(experience|knowledge|degree|bachelor|master|proficient|familiar|required|preferred)\b", re.I)
SPLIT_DELIMS = re.compile(r"(?:\r?\n|\u2022|•|;|(?<=\.)\s+)")

TECH_TOKENS = [
    "python", "java", "c++", "c#", "go", "typescript", "javascript", "react", "node", "spring",
    "docker", "kubernetes", "aws", "azure", "gcp", "sql", "postgres", "mysql", "mongodb",
    "terraform", "linux", "git", "ci/cd", "ros", "opencv", "pytorch", "tensorflow", "fastapi",
]


def _extract_title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.text:
        return soup.title.text.strip()
    h1 = soup.find("h1")
    return h1.text.strip() if h1 else None


def _extract_meta_description(soup: BeautifulSoup) -> str | None:
    for sel in [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ]:
        tag = soup.find("meta", attrs=sel)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _extract_company(soup: BeautifulSoup) -> str | None:
    # Heuristic: try common selectors
    for sel in [
        {"itemprop": "hiringOrganization"},
        {"data-test": "job-details__company"},
        {"class": re.compile(r"company|employer", re.I)},
    ]:
        tag = soup.find(attrs=sel)
        if tag and tag.get_text(strip=True):
            return tag.get_text(strip=True)
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None


def _extract_from_json_ld(soup: BeautifulSoup):
    """Extract fields from JSON-LD JobPosting blocks if present."""
    title = company = location = None
    responsibilities: list[str] = []
    requirements: list[str] = []
    descriptions: list[str] = []

    for script in soup.find_all("script", type=lambda v: v and "ld+json" in v):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Some sites embed multiple JSON objects; try to fix common issues
            try:
                data = json.loads(raw.strip().strip(";"))
            except Exception:
                continue

        def handle_jobposting(obj):
            nonlocal title, company, location, responsibilities, requirements, descriptions
            if not isinstance(obj, dict):
                return
            t = obj.get("@type") or obj.get("type")
            if isinstance(t, list):
                t = ",".join(t)
            if not t or "JobPosting" not in str(t):
                return
            title = title or obj.get("title")
            org = obj.get("hiringOrganization") or {}
            if isinstance(org, dict):
                company = company or org.get("name")
            loc = obj.get("jobLocation") or {}
            if isinstance(loc, dict):
                addr = loc.get("address") or {}
                if isinstance(addr, dict):
                    location = location or (
                        ", ".join(filter(None, [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]))
                    )
            desc = obj.get("description")
            if isinstance(desc, str) and desc.strip():
                # Strip HTML tags from description
                text = BeautifulSoup(desc, "lxml").get_text("\n", strip=True)
                descriptions.append(text)
            resp = obj.get("responsibilities")
            if isinstance(resp, list):
                responsibilities.extend([str(x).strip() for x in resp if str(x).strip()])
            elif isinstance(resp, str):
                responsibilities.extend([s.strip() for s in re.split(r"[\n•\-\*]", resp) if s.strip()])
            quals = obj.get("qualifications") or obj.get("experienceRequirements")
            if isinstance(quals, list):
                requirements.extend([str(x).strip() for x in quals if str(x).strip()])
            elif isinstance(quals, str):
                requirements.extend([s.strip() for s in re.split(r"[\n•\-\*]", quals) if s.strip()])

        # Data may be a dict, list, or nested graph
        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                for node in data["@graph"]:
                    handle_jobposting(node)
            else:
                handle_jobposting(data)
        elif isinstance(data, list):
            for item in data:
                handle_jobposting(item)

    return title, company, location, responsibilities, requirements, descriptions


def _seek_dom_fields(soup: BeautifulSoup):
    """Seek DOM selectors for title/company/location when available."""
    title = company = location = None
    t = soup.select_one('[data-automation="job-detail-title"]')
    if t and t.get_text(strip=True):
        title = t.get_text(strip=True)
    c = soup.select_one('[data-automation="advertiser-name"]')
    if c and c.get_text(strip=True):
        company = c.get_text(strip=True)
    loc = soup.select_one('[data-automation="job-detail-location"]')
    if loc and loc.get_text(strip=True):
        location = loc.get_text(strip=True)
    return title, company, location


def _extract_lists_by_headings(soup: BeautifulSoup):
    responsibilities, requirements, benefits = [], [], []
    for header in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = header.get_text(" ", strip=True)
        nxt = header.find_next_sibling()
        while nxt and nxt.name in ["br", "hr"]:
            nxt = nxt.find_next_sibling()
        if not nxt:
            continue
        items = []
        if nxt.name in ["ul", "ol"]:
            items = [li.get_text(" ", strip=True) for li in nxt.find_all("li")]
        elif nxt.name == "p":
            # sometimes bullet-like paragraphs
            items = [nxt.get_text(" ", strip=True)]
        if not items:
            continue
        if HEADINGS_RESP.search(text):
            responsibilities.extend(items)
        elif HEADINGS_REQ.search(text):
            requirements.extend(items)
    return responsibilities, requirements, benefits


def _extract_generic_lists(soup: BeautifulSoup):
    resps, reqs = [], []
    for ul in soup.find_all("ul"):
        for li in ul.find_all("li"):
            t = li.get_text(" ", strip=True)
            if not t or len(t) < 3:
                continue
            if RESP_VERBS.search(t):
                resps.append(t)
            elif REQ_TOKENS.search(t):
                reqs.append(t)
    return resps, reqs


def _extract_keywords(texts: list[str]) -> list[str]:
    kw = set()
    lowtexts = "\n".join(texts).lower()
    for token in TECH_TOKENS:
        if token in lowtexts:
            kw.add(token.upper() if token in ["aws", "gcp", "sql", "ros"] else token.capitalize())
    return sorted(kw)


def _filter_questions(items: list[str]) -> list[str]:
    out = []
    for s in items:
        s_clean = s.strip()
        low = s_clean.lower()
        if not s_clean:
            continue
        if s_clean.endswith("?"):
            continue
        if low.startswith("how many") or low.startswith("how much") or low.startswith("what is") or low.startswith("what's") or low.startswith("when can") or low.startswith("do you"):
            continue
        out.append(s_clean)
    return out


def _split_compound_items(items: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in items or []:
        if not item:
            continue
        text = item.strip()
        if not text:
            continue
        base = text
        if ":" in base:
            head, tail = base.split(":", 1)
            if len(head.split()) <= 6 and tail.strip():
                base = tail.strip()
        segments = SPLIT_DELIMS.split(base)
        parts = []
        for seg in segments:
            seg = seg.strip(" .;,-\u2022")
            if len(seg) > 3:
                parts.append(seg)
        if parts:
            expanded.extend(parts)
        else:
            expanded.append(text)
    # preserve order while deduplicating
    return list(dict.fromkeys(expanded))


def _walk_json(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_json(it)


def _parse_seek_next_data(soup: BeautifulSoup) -> Tuple[str | None, str | None, str | None, list[str], list[str], list[str]]:
    """Extract info from Next.js __NEXT_DATA__ on Seek job pages."""
    title = company = location = None
    responsibilities: list[str] = []
    requirements: list[str] = []
    descriptions: list[str] = []

    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return title, company, location, responsibilities, requirements, descriptions
    try:
        data = json.loads(script.string)
    except Exception:
        return title, company, location, responsibilities, requirements, descriptions

    for node in _walk_json(data):
        # Title candidates
        for k in ["jobTitle", "title"]:
            if isinstance(node, dict) and k in node and isinstance(node[k], str) and len(node[k]) > 2:
                title = title or node[k].strip()
        # Company candidates
        if isinstance(node, dict):
            adv = node.get("advertiser") or node.get("company") or node.get("hiringOrganization")
            if isinstance(adv, dict):
                nm = adv.get("name") or adv.get("companyName")
                if isinstance(nm, str) and nm.strip():
                    company = company or nm.strip()
        # Location candidates
        if isinstance(node, dict) and "location" in node and isinstance(node["location"], str):
            if len(node["location"]) > 1:
                location = location or node["location"].strip()
        # Lists of strings as bullets
        if isinstance(node, list) and node and all(isinstance(x, str) for x in node):
            texts = [x.strip() for x in node if len(x.strip()) > 3]
            if not texts:
                continue
            # classify via regex cues
            for t in texts:
                if RESP_VERBS.search(t):
                    responsibilities.append(t)
                elif REQ_TOKENS.search(t):
                    requirements.append(t)
            # If neither classifier matched, treat as description pool
            descriptions.extend(texts)
        # Rich descriptions
        for k in ["description", "content", "body"]:
            if isinstance(node, dict) and k in node and isinstance(node[k], str):
                text = BeautifulSoup(node[k], "lxml").get_text("\n", strip=True)
                if len(text) > 10:
                    descriptions.append(text)

    # de-dup
    responsibilities = list(dict.fromkeys(responsibilities))
    requirements = list(dict.fromkeys(requirements))
    descriptions = list(dict.fromkeys(descriptions))
    return title, company, location, responsibilities, requirements, descriptions


def parse_html_to_jd(html: str, url: str | None = None) -> ParsedJD:
    soup = BeautifulSoup(html, "lxml")

    # Try JSON-LD JobPosting first (works for many job sites including LinkedIn/Seek variants)
    t_ld, c_ld, loc_ld, resp_ld, req_ld, desc_ld = _extract_from_json_ld(soup)

    # Site-specific: Seek Next.js data
    t_seek = c_seek = loc_seek = None
    resp_seek: list[str] = []
    req_seek: list[str] = []
    desc_seek: list[str] = []
    if url and "seek.com.au" in url:
        t_seek, c_seek, loc_seek, resp_seek, req_seek, desc_seek = _parse_seek_next_data(soup)

    title = t_seek or t_ld or _extract_title(soup)
    company = c_seek or c_ld or _extract_company(soup)
    location = loc_seek or loc_ld

    # If still missing seek-specific fields, try DOM selectors
    if (not title or not company or not location) and (url and "seek.com.au" in url):
        td, cd, ld = _seek_dom_fields(soup)
        title = title or td
        company = company or cd
        location = location or ld

    # Heuristic section extraction from headings and generic lists
    resp_h, req_h, _ = _extract_lists_by_headings(soup)
    resp_g, req_g = _extract_generic_lists(soup)

    responsibilities = list(dict.fromkeys([*resp_seek, *resp_ld, *resp_h, *resp_g]))[:80]
    requirements = list(dict.fromkeys([*req_seek, *req_ld, *req_h, *req_g]))[:80]

    # If still empty, try splitting description bullets (including meta description)
    if not responsibilities:
        meta_desc = _extract_meta_description(soup)
        if meta_desc:
            if desc_ld is None:
                desc_ld = []
            desc_ld.append(meta_desc)
    # merge desc pools
    if desc_ld is None:
        desc_ld = []
    desc_ld.extend(desc_seek)
    if not responsibilities and desc_ld:
        bullets = []
        for d in desc_ld:
            bullets.extend([s.strip() for s in re.split(r"[\n•\-\*]", d) if len(s.strip()) > 3])
        # classify roughly by verbs/tokens
        for b in bullets:
            if RESP_VERBS.search(b):
                responsibilities.append(b)
            elif REQ_TOKENS.search(b):
                requirements.append(b)
    responsibilities = _split_compound_items(responsibilities)
    requirements = _split_compound_items(requirements)
    responsibilities = _filter_questions(responsibilities)[:80]
    requirements = _filter_questions(requirements)[:80]

    keywords = _extract_keywords([*responsibilities, *requirements, *(desc_ld or [])])

    return ParsedJD(
        title=title,
        company=company,
        location=location,
        responsibilities=responsibilities,
        requirements=requirements,
        keywords=keywords,
    )
