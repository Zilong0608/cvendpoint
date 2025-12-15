from typing import List
from urllib.parse import urlparse

from modules.agent.tools import web_search
from modules.shared.utils import dedup_hash, canonical_url, is_job_result_inactive
from ..schemas import Job, JobQuery

_FRESH_INDICATORS = ["hour", "hours", "day", "days", "today", "new", "just", "1d"]
_STALE_INDICATORS = ["week", "weeks", "month", "months", "year", "years", "expired", "ago"]


def _build_query(q: JobQuery) -> str:
    parts = []
    if q.titles:
        parts.append("(" + " OR ".join(q.titles) + ")")
    if q.keywords:
        parts.append("(" + " OR ".join(q.keywords) + ")")
    if q.locations:
        parts.append("(" + " OR ".join(q.locations) + ")")
    parts.append("site:linkedin.com/jobs")
    return " ".join(parts)


def _is_posting_fresh(result: dict) -> bool:
    posted = (result.get("posted_at") or "").strip().lower()
    snippet = (result.get("snippet") or "").strip().lower()

    if posted:
        if any(ind in posted for ind in _STALE_INDICATORS if ind not in {"ago"}):
            if not any(ind in posted for ind in _FRESH_INDICATORS):
                return False
        if posted.isdigit():
            return False
        if "ago" in posted and not any(ind in posted for ind in _FRESH_INDICATORS):
            return False

    if snippet:
        if "month ago" in snippet or "months ago" in snippet or "year ago" in snippet or "years ago" in snippet:
            return False
        if "week ago" in snippet or "weeks ago" in snippet:
            return False
        if "expired" in snippet or "closed" in snippet:
            return False

    return True


def search_linkedin(query: JobQuery, limit: int = 50, exclude_hashes: List[str] | None = None) -> List[Job]:
    exclude = set(exclude_hashes or [])
    q = _build_query(query)
    top_k = max(limit * 3, limit or 1)
    results = web_search(q, top_k=top_k, region="AU") or []
    jobs: List[Job] = []
    for r in results:
        if is_job_result_inactive(r):
            continue
        if not _is_posting_fresh(r):
            continue
        url = canonical_url(r.get("url", ""))
        if not url:
            continue
        domain = urlparse(url).netloc.lower()
        if "linkedin.com" not in domain:
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
                source="linkedin",
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
