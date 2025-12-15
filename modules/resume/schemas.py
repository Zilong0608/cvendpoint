from typing import Optional
from pydantic import BaseModel
from modules.profile.schemas import Profile
from modules.jd.schemas import ParsedJD


class RenderInput(BaseModel):
    profile: Profile
    jd: Optional[ParsedJD] = None
    template_id: str = "resume-ats-en"
    language: str = "en"
    polish: bool = True


class RenderOutput(BaseModel):
    html: str
    meta: dict = {}


class HtmlInput(BaseModel):
    html: str


class RefineOptions(BaseModel):
    tone: str = "impactful"  # impactful | concise | formal
    tense: str = "past"       # past | present
    max_bullets_per_role: int = 5
    include_jd_keywords: bool = True


class RefineInput(BaseModel):
    profile: Profile
    jd: Optional[ParsedJD] = None
    options: RefineOptions = RefineOptions()


class RefineOutput(BaseModel):
    profile: Profile
    summary: Optional[str] = None
    notes: list[str] = []
