from typing import List, Optional, Dict
from pydantic import BaseModel


class Course(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    topics: List[str] = []
    skills: List[str] = []
    tools: List[str] = []


class Education(BaseModel):
    school: str
    degree: Optional[str] = None
    major: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class Experience(BaseModel):
    company: str
    role: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    bullets: List[str] = []


class Profile(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    education: List[Education] = []
    experience: List[Experience] = []
    projects: List[Experience] = []
    skills: List[str] = []
    courses: List[Course] = []
    languages: List[str] = []
    target_roles: List[str] = []
    target_locations: List[str] = []


class AnalyzeProfileInput(BaseModel):
    free_text: Optional[str] = None
    education: List[Education] = []
    experience: List[Experience] = []
    courses: List[Course] = []
    skills: List[str] = []


class RoleRecommendation(BaseModel):
    title: str
    reason: str
    matched_keywords: List[str] = []


class AnalyzeProfileOutput(BaseModel):
    profile: Profile
    normalized_skills: List[str] = []
    course_enrichment_notes: List[str] = []
    keywords: List[str] = []
    course_skills: Dict[str, List[str]] = {}
    role_recommendations: List[RoleRecommendation] = []


class RoleRecommendationsInput(BaseModel):
    profile: Profile
    limit: Optional[int] = 5


class RoleRecommendationsOutput(BaseModel):
    role_recommendations: List[RoleRecommendation] = []
