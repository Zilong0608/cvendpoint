from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from .schemas import (
    AnalyzeProfileInput,
    AnalyzeProfileOutput,
    Profile,
    RoleRecommendationsInput,
    RoleRecommendationsOutput,
)
from .service import analyze_profile, recommend_roles_for_profile
from .extract import extract_text_from_upload, analyze_text_to_profile, merge_profiles, englishize_skills
from .llm_map import strict_map_profile
from .text_preserve import parse_text_preserve
# preserve-first parsing is disabled in this path to avoid docx incompat issues
from .enrich_db import enrich_courses_from_text_db
from .postprocess import normalize_contact_location, normalize_education, normalize_experience_projects, canonicalize_skill_list


router = APIRouter()


@router.post("/analyze", response_model=AnalyzeProfileOutput)
def analyze(input: AnalyzeProfileInput):
    return analyze_profile(input)


@router.post("/analyze-upload", response_model=AnalyzeProfileOutput)
async def analyze_upload(
    file: UploadFile | None = File(default=None),
    free_text: str = Form(default=""),
    use_llm_strict_map: bool = Form(default=False),
):
    if not file and not free_text:
        raise HTTPException(status_code=400, detail="file or free_text required")

    file_profile: Profile | None = None
    notes: list[str] = []
    texts_for_enrich: list[str] = []
    uploaded = False
    if file is not None:
        # Extract text from file (pdf/docx/html). Avoid docx style pitfalls.
        text, n = extract_text_from_upload(file)
        notes.extend(n)
        if text:
            uploaded = True
            texts_for_enrich.append(text)
            # Prefer robust text-preserve parser; fallback to analyzer
            prof_dict_t, _plain = parse_text_preserve(text)
            if prof_dict_t and any((prof_dict_t.get('education') or prof_dict_t.get('experience') or prof_dict_t.get('projects'))):
                file_profile = Profile(**prof_dict_t)
                notes.append('text_preserve_ok')
            else:
                p, n2 = analyze_text_to_profile(text)
                notes.extend(n2)
                file_profile = p
        else:
            if any(k.startswith('doc_legacy_format_not_fully_supported') for k in n):
                raise HTTPException(status_code=415, detail='.doc legacy not fully supported. Please upload PDF/DOCX/HTML.')

    text_profile: Profile | None = None
    if free_text and free_text.strip():
        texts_for_enrich.append(free_text)
        p, n3 = analyze_text_to_profile(free_text)
        notes.extend(n3)
        text_profile = p

    # Merge profiles: file preferred
    if file_profile and text_profile:
        prof = merge_profiles(file_profile, text_profile)
    else:
        prof = file_profile or text_profile

    if prof is None:
        raise HTTPException(status_code=400, detail="No usable content")

    # Optional strict LLM mapping (non-rewrite). Preserve bullets strictly.
    if use_llm_strict_map and prof is not None:
        mapped, map_notes = strict_map_profile(prof)
        try:
            school_to_idx = { (e.school or '').lower(): i for i,e in enumerate(prof.education or []) }
            for i, e2 in enumerate(mapped.education or []):
                key = (e2.school or '').lower()
                j = school_to_idx.get(key)
                if j is not None:
                    src = mapped.education[i]
                    dst = prof.education[j]
                    if src.degree: dst.degree = src.degree
                    if src.major: dst.major = src.major
                    if src.start: dst.start = src.start
                    if src.end: dst.end = src.end
            for i in range(min(len(prof.experience or []), len(mapped.experience or []))):
                src = mapped.experience[i]
                dst = prof.experience[i]
                if src.company: dst.company = src.company
                if src.role: dst.role = src.role
                if src.start: dst.start = src.start
                if src.end: dst.end = src.end
            notes.extend(map_notes)
        except Exception:
            notes.append('llm_map_merge_error')

    # Keep existing skills as-is when uploaded; otherwise normalize basic casing
    if not uploaded:
        prof.skills = englishize_skills(prof.skills or [])

    # Enrich courses from DB: combine text-detected codes + profile.courses codes
    if texts_for_enrich:
        extra_codes = [c.code for c in (prof.courses or []) if getattr(c, 'code', None)]
        courses, cnotes = enrich_courses_from_text_db(texts_for_enrich, extra_codes=extra_codes)
        notes.extend(cnotes)
        # Build course_skills mapping and merge skills
        course_skills: dict[str, list[str]] = {}
        if courses:
            for c in courses:
                if not c.code:
                    continue
                # canonicalize new skills phrases only
                skills = englishize_skills(c.skills or [])
                skills = canonicalize_skill_list(skills)
                if skills:
                    course_skills[c.code.upper()] = skills
            if course_skills:
                # merge new skills without altering original ones
                merged = (prof.skills or []) + [s for v in course_skills.values() for s in v]
                # de-dup case-insensitive
                seen = set()
                prof.skills = []
                for s in merged:
                    k = (s or '').lower()
                    if k in seen:
                        continue
                    seen.add(k)
                    prof.skills.append(s)
            # sanitize courses on profile: keep only code
            prof.courses = [type(c)(code=c.code, name=None, topics=[], skills=[], tools=[]) for c in (prof.courses or [])]
        else:
            course_skills = {}

    # Final post-processing to fit resume template
    try:
        # Uploaded resume: do not change contact/location/education/experience
        if not uploaded:
            normalize_contact_location(prof, base_text=free_text or "")
            normalize_education(prof, base_text=free_text or "")
            normalize_experience_projects(prof)
            prof.skills = canonicalize_skill_list(prof.skills or [])
    except Exception:
        pass

    # Clean simple location prefix like 'Address:'
    if prof.location and prof.location.lower().startswith('address:'):
        prof.location = prof.location.split(':',1)[1].strip()

    return AnalyzeProfileOutput(
        profile=prof,
        normalized_skills=prof.skills or [],
        course_enrichment_notes=notes,
        keywords=prof.skills or [],
        course_skills=course_skills if texts_for_enrich else {},
    )


@router.post("/recommend-roles", response_model=RoleRecommendationsOutput)
def recommend_roles_endpoint(payload: RoleRecommendationsInput):
    if payload.profile is None:
        raise HTTPException(status_code=400, detail="profile required")
    recommendations = recommend_roles_for_profile(payload.profile)
    if payload.limit is not None and payload.limit >= 0:
        recommendations = recommendations[: payload.limit]
    return RoleRecommendationsOutput(role_recommendations=recommendations)


