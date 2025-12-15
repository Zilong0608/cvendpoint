from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from .schemas import SearchJobsInput, SearchJobsOutput, JobQuery
from .search import search_jobs
from .stream import stream_jobs


router = APIRouter()


@router.post("/search", response_model=SearchJobsOutput)
def search(input: SearchJobsInput):
    return search_jobs(input)


@router.post("/next-batch", response_model=SearchJobsOutput)
def next_batch(input: SearchJobsInput):
    # Same signature, caller provides updated exclude_hashes to avoid overlap
    return search_jobs(input)


@router.post("/stream")
def stream(input: SearchJobsInput):
    generator = stream_jobs(input)
    return StreamingResponse(generator, media_type="text/event-stream")


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


@router.get("/stream")
def stream_get(
    session_id: str = Query(default=""),
    titles: str = Query(default=""),
    keywords: str = Query(default=""),
    locations: str = Query(default="AU"),
    seek: int = Query(default=5, ge=0, le=50),
    linkedin: int = Query(default=5, ge=0, le=50),
    limit: int = Query(default=10, ge=1, le=100),
):
    input = SearchJobsInput(
        session_id=session_id or None,
        query=JobQuery(titles=_csv(titles), keywords=_csv(keywords), locations=_csv(locations)),
        allocation={"seek": seek, "linkedin": linkedin},
        limit=limit,
        exclude_hashes=[],
    )
    generator = stream_jobs(input)
    return StreamingResponse(generator, media_type="text/event-stream")
