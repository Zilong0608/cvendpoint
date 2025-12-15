from typing import List, Dict, Tuple
from .schemas import SearchJobsInput, SearchJobsOutput, Job
from .adapters.seek import search_seek
from .adapters.linkedin import search_linkedin
from .session import get_seen, add_seen


def _hash_key(title: str, company: str, location: str, url: str) -> str:
    import hashlib
    key = f"{title.strip().lower()}|{company.strip().lower()}|{(location or '').strip().lower()}|{(url or '').strip().lower()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _dedupe(jobs: List[Job], exclude: List[str]) -> Tuple[List[Job], List[str]]:
    seen = set(exclude)
    out: List[Job] = []
    added_hashes: List[str] = []
    for j in jobs:
        if j.hash in seen:
            continue
        seen.add(j.hash)
        out.append(j)
        added_hashes.append(j.hash)
    return out, added_hashes


def search_jobs(payload: SearchJobsInput) -> SearchJobsOutput:
    requested = payload.limit
    alloc = payload.allocation or {}
    # Merge client-provided excludes with session-level seen set (if any)
    exclude = list(payload.exclude_hashes or [])
    if payload.session_id:
        exclude = list(set(exclude) | get_seen(payload.session_id))

    # Call adapters per allocation
    jobs: List[Job] = []
    if alloc.get("seek", 0) > 0:
        jobs.extend(search_seek(payload.query, alloc.get("seek", 0), exclude_hashes=exclude))
    if alloc.get("linkedin", 0) > 0:
        jobs.extend(search_linkedin(payload.query, alloc.get("linkedin", 0), exclude_hashes=exclude))

    # Deduplicate and honor exclude list
    unique, added_hashes = _dedupe(jobs, exclude)

    # If not enough, we simply return what's available (后续可做回退策略)
    limited = unique[:requested]
    # Record seen hashes into session store for future batches
    if payload.session_id and limited:
        add_seen(payload.session_id, [j.hash for j in limited])
    stats = {
        "requested": requested,
        "by_source": alloc,
        "deduped": len(jobs) - len(unique),
        "total": len(limited),
    }
    return SearchJobsOutput(jobs=limited, seen_hashes=added_hashes, stats=stats)
