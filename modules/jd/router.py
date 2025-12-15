from fastapi import APIRouter
from .schemas import FetchJDInput, FetchJDOutput
from .fetcher import fetch_and_parse


router = APIRouter()


@router.post("/fetch", response_model=FetchJDOutput)
def fetch(input: FetchJDInput):
    result = fetch_and_parse(input.jd_url, render=input.render)
    if isinstance(result, tuple):
        jd, dbg = result
    else:
        jd, dbg = result, None
    return FetchJDOutput(jd=jd, debug=(dbg if input.debug else None))
