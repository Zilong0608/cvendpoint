from fastapi import APIRouter
from .schemas import MatchInput, MatchResult
from .engine import match as run_match


router = APIRouter()


@router.post("/match", response_model=MatchResult)
def match(input: MatchInput):
    return run_match(input)

