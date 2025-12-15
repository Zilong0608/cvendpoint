from typing import List, Optional, Dict
from pydantic import BaseModel, HttpUrl


class Job(BaseModel):
    id: str
    hash: str
    source: str  # seek | linkedin
    title: str
    company: str
    location: Optional[str] = None
    remote: Optional[bool] = None
    jd_url: Optional[str] = None
    posted_at: Optional[str] = None
    keywords: List[str] = []


class JobQuery(BaseModel):
    titles: List[str] = []
    keywords: List[str] = []
    locations: List[str] = []  # default AU; user can override
    seniority: Optional[str] = None
    remote: Optional[bool] = None


class SearchJobsInput(BaseModel):
    query: JobQuery
    sources: List[str] = ["seek", "linkedin"]
    allocation: Dict[str, int] = {"seek": 5, "linkedin": 5}
    limit: int = 10
    exclude_hashes: List[str] = []
    session_id: Optional[str] = None


class SearchJobsOutput(BaseModel):
    jobs: List[Job] = []
    seen_hashes: List[str] = []
    stats: dict = {}
