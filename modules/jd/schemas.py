from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class ParsedJD(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    responsibilities: List[str] = []
    requirements: List[str] = []
    benefits: List[str] = []
    keywords: List[str] = []


class FetchJDInput(BaseModel):
    jd_url: str
    debug: bool = False
    render: bool = False


class FetchJDOutput(BaseModel):
    jd: ParsedJD
    debug: Optional[Dict[str, Any]] = None
