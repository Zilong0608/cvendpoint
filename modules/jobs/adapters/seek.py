from typing import List
from urllib.parse import urlparse

from modules.agent.tools import web_search
from modules.shared.utils import dedup_hash, canonical_url, is_job_result_inactive
from ..schemas import Job, JobQuery


def _build_query(q: JobQuery) -> str:
    parts = []
    if q.titles:
        parts.append("(" + " OR ".join(q.titles) + ")")
    if q.keywords:
        parts.append("(" + " OR ".join(q.keywords) + ")")
    # AU focus by default; site limited to seek
    if q.locations:
        parts.append("(" + " OR ".join(q.locations) + ")")
    parts.append("site:seek.com.au")
    return " ".join(parts)


def search_seek(query: JobQuery, limit: int = 50, exclude_hashes: List[str] | None = None) -> List[Job]:
    exclude = set(exclude_hashes or [])
    q = _build_query(query)
    top_k = max(limit * 3, limit or 1)
    results = web_search(q, top_k=top_k, region="AU") or []
    jobs: List[Job] = []
    for r in results:
        if is_job_result_inactive(r):
            continue
        url = canonical_url(r.get("url", ""))
        if not url:
            continue
        domain = urlparse(url).netloc.lower()
        if "seek.com" not in domain:
            continue
        title = r.get("title") or "Job"
        company = r.get("company") or ""
        location = r.get("location") or (query.locations[0] if query.locations else "")
        h = dedup_hash(title, company, location, url)
        if h in exclude:
            continue
        jobs.append(
            Job(
                id=h,
                hash=h,
                source="seek",
                title=title,
                company=company,
                location=location,
                jd_url=url,
                posted_at=r.get("posted_at"),
                keywords=query.keywords or [],
            )
        )
        if len(jobs) >= limit:
            break
    return jobs
