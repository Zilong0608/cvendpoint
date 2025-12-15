from typing import List
from pydantic import BaseModel
from modules.profile.schemas import Profile
from modules.jd.schemas import ParsedJD


class MatchInput(BaseModel):
    profile: Profile
    jd: ParsedJD


class MatchResult(BaseModel):
    score: int = 0
    reasons: List[str] = []
    gaps: List[str] = []
    recommendations: List[str] = []

