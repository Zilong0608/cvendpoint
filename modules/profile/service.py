import re
from typing import List, Tuple
from .schemas import AnalyzeProfileInput, AnalyzeProfileOutput, Profile, RoleRecommendation
from .extract import analyze_text_to_profile, englishize_skills
from .enrich_db import enrich_courses_from_text_db
from .postprocess import normalize_contact_location, normalize_education, normalize_experience_projects, canonicalize_skill_list


ROLE_RULES: List[Tuple[str, List[str], int]] = [
    (
        "Software Engineer",
        [
            "python",
            "java",
            "c++",
            "c#",
            "go",
            "fastapi",
            "django",
            "flask",
            "spring",
            "api",
            "microservice",
            "object oriented",
            "oop",
            "design pattern",
        ],
        2,
    ),
    (
        "Backend Engineer",
        [
            "python",
            "java",
            "node",
            "fastapi",
            "django",
            "flask",
            "spring",
            "api",
            "graphql",
            "database",
            "postgres",
            "mysql",
            "redis",
            "rest",
            "microservice",
        ],
        2,
    ),
    (
        "前端工程师 Frontend Engineer",
        [
            "javascript",
            "typescript",
            "react",
            "vue",
            "angular",
            "html",
            "css",
            "sass",
            "webpack",
            "vite",
            "frontend",
            "ui",
            "ux",
            "页面",
        ],
        2,
    ),
    (
        "全栈工程师 Full Stack Engineer",
        [
            "fullstack",
            "full-stack",
            "react",
            "vue",
            "angular",
            "node",
            "express",
            "nestjs",
            "graphql",
            "fastapi",
            "django",
            "flask",
            "mysql",
            "postgres",
            "mongodb",
            "rest api",
        ],
        2,
    ),
    (
        "DevOps / SRE Engineer",
        [
            "devops",
            "sre",
            "site reliability",
            "ci",
            "cd",
            "jenkins",
            "github actions",
            "gitlab ci",
            "terraform",
            "ansible",
            "kubernetes",
            "docker",
            "helm",
            "infrastructure",
            "monitoring",
            "prometheus",
            "grafana",
        ],
        2,
    ),
    (
        "云原生工程师 Cloud Engineer",
        [
            "aws",
            "azure",
            "gcp",
            "cloudformation",
            "lambda",
            "eks",
            "ecs",
            "cloudwatch",
            "cloud engineer",
            "serverless",
            "cloud run",
            "cloud storage",
        ],
        2,
    ),
    (
        "移动开发工程师 Mobile Engineer",
        [
            "ios",
            "android",
            "swift",
            "kotlin",
            "react native",
            "flutter",
            "objective-c",
            "mobile",
            "app store",
            "play store",
        ],
        2,
    ),
    (
        "QA / 测试工程师 Test Engineer",
        [
            "qa",
            "quality assurance",
            "测试",
            "automation",
            "自动化测试",
            "selenium",
            "cypress",
            "playwright",
            "pytest",
            "integration test",
            "unit test",
            "regression",
        ],
        2,
    ),
    (
        "数据分析师 Data Analyst",
        [
            "sql",
            "excel",
            "tableau",
            "power bi",
            "analysis",
            "analytics",
            "pandas",
            "lookml",
            "dashboard",
            "insight",
            "数据分析",
            "数据可视化",
        ],
        2,
    ),
    (
        "数据科学家 Data Scientist",
        [
            "data science",
            "统计",
            "statistics",
            "machine learning",
            "ml",
            "python",
            "r",
            "pandas",
            "numpy",
            "scikit",
            "model",
            "预测",
            "预测模型",
        ],
        2,
    ),
    (
        "数据工程师 Data Engineer",
        [
            "spark",
            "pyspark",
            "etl",
            "elt",
            "airflow",
            "kafka",
            "data pipeline",
            "aws glue",
            "databricks",
            "snowflake",
            "bigquery",
            "data warehouse",
        ],
        2,
    ),
    (
        "机器学习工程师 ML Engineer",
        [
            "machine learning",
            "ml",
            "pytorch",
            "tensorflow",
            "scikit",
            "model",
            "training",
            "spark",
            "mlops",
            "model serving",
            "fine-tune",
            "huggingface",
        ],
        2,
    ),
    (
        "大模型工程师 LLM Engineer",
        [
            "llm",
            "large language model",
            "prompt",
            "embedding",
            "rag",
            "langchain",
            "transformer",
            "gpt",
            "llama",
            "finetune",
            "chatbot",
        ],
        2,
    ),
    (
        "商业分析师 Business Analyst",
        [
            "business analysis",
            "stakeholder",
            "requirement",
            "需求分析",
            "流程",
            "process",
            "gap analysis",
            "report",
            "powerpoint",
            "利益相关者",
        ],
        2,
    ),
    (
        "产品经理 Product Manager",
        [
            "product",
            "roadmap",
            "stakeholder",
            "user research",
            "需求",
            "原型",
            "wireframe",
            "prio",
            "mvp",
            "go-to-market",
        ],
        2,
    ),
    (
        "项目经理 Project Manager",
        [
            "project management",
            "pm",
            "scrum",
            "敏捷",
            "agile",
            "kanban",
            "jira",
            "confluence",
            "timeline",
            "budget",
            "资源管理",
        ],
        2,
    ),
    (
        "安全工程师 Security Engineer",
        [
            "security",
            "appsec",
            "pentest",
            "漏洞",
            "owasp",
            "threat",
            "iam",
            "zero trust",
            "siem",
            "soc",
            "渗透",
        ],
        2,
    ),
]


def normalize_skills(skills: List[str]) -> List[str]:
    # TODO: map synonyms to canonical forms
    return sorted(set([s.strip() for s in skills if s and s.strip()]))


def _tokenize_text(text: str) -> List[str]:
    return re.findall(r"[a-z0-9\+#\.]+", text.lower())


def _collect_profile_tokens(profile: Profile, normalized_skills: List[str]) -> Tuple[set[str], str]:
    tokens: set[str] = set(s.lower() for s in normalized_skills)
    text_chunks: List[str] = []

    for edu in profile.education or []:
        for field in (edu.school, edu.degree, edu.major):
            if field:
                text_chunks.append(field)
    for exp in profile.experience or []:
        if exp.role:
            tokens.add(exp.role.lower())
            text_chunks.append(exp.role)
        for bullet in exp.bullets or []:
            text_chunks.append(bullet)
            tokens.update(_tokenize_text(bullet))
    for proj in profile.projects or []:
        if proj.role:
            tokens.add(proj.role.lower())
            text_chunks.append(proj.role)
        for bullet in proj.bullets or []:
            text_chunks.append(bullet)
            tokens.update(_tokenize_text(bullet))
    for course in profile.courses or []:
        for field in (course.name, *(course.topics or []), *(course.skills or []), *(course.tools or [])):
            if field:
                text_chunks.append(field)
                tokens.update(_tokenize_text(field))
    for lang in profile.languages or []:
        tokens.add(lang.lower())
    text_blob = " ".join(text_chunks).lower()
    tokens.update(_tokenize_text(text_blob))
    return tokens, text_blob


def _build_role_recommendations(profile: Profile, normalized_skills: List[str]) -> List[RoleRecommendation]:
    tokens, text_blob = _collect_profile_tokens(profile, normalized_skills)
    lower_to_display = {s.lower(): s for s in normalized_skills}

    recommendations: List[Tuple[str, List[str]]] = []
    for title, keywords, min_hits in ROLE_RULES:
        matched: List[str] = []
        for kw in keywords:
            kw_l = kw.lower()
            if " " in kw_l:
                if kw_l in text_blob:
                    matched.append(kw)
            else:
                if kw_l in tokens:
                    matched.append(kw)
        if len(set(matched)) >= min_hits:
            display_matches = []
            seen = set()
            for key in matched:
                key_l = key.lower()
                if key_l in seen:
                    continue
                seen.add(key_l)
                display = lower_to_display.get(key_l) or key
                display_matches.append(display)
            if display_matches:
                recommendations.append((title, display_matches))

    # Deduplicate by title, keep order by number of matches descending
    unique_recommendations = []
    seen_titles = set()
    for title, matches in sorted(recommendations, key=lambda x: len(x[1]), reverse=True):
        if title in seen_titles:
            continue
        seen_titles.add(title)
        reason = f"匹配关键词：{', '.join(matches[:5])}"
        unique_recommendations.append(RoleRecommendation(title=title, reason=reason, matched_keywords=matches))

    return unique_recommendations[:5]


def recommend_roles_for_profile(profile: Profile, normalized_skills: List[str] | None = None) -> List[RoleRecommendation]:
    skills = normalized_skills if normalized_skills is not None else canonicalize_skill_list(englishize_skills(profile.skills or []))
    return _build_role_recommendations(profile, skills)


def analyze_profile(payload: AnalyzeProfileInput) -> AnalyzeProfileOutput:
    # If free_text present, attempt to parse with LLM (or rule-based fallback)
    notes = []
    profile = None
    if payload.free_text:
        prof, n = analyze_text_to_profile(payload.free_text)
        profile = prof
        notes.extend(n)
    # Merge structured fields
    normalized_skills = normalize_skills((payload.skills or []) + (profile.skills if profile else []))
    profile = Profile(
        name=(profile.name if profile else None),
        contact=(profile.contact if profile else None),
        location=(profile.location if profile else None),
        education=(payload.education or []) + (profile.education if profile else []),
        experience=(payload.experience or []) + (profile.experience if profile else []),
        courses=(payload.courses or []) + (profile.courses if profile else []),
        skills=normalized_skills,
    )
    # Course enrichment from free_text if present
    course_skills: dict[str, list[str]] = {}
    if payload.free_text or (profile and profile.courses):
        extra_codes = [c.code for c in (profile.courses or []) if getattr(c, 'code', None)]
        courses, cnotes = enrich_courses_from_text_db([payload.free_text] if payload.free_text else [], extra_codes=extra_codes)
        notes.extend(cnotes)
        if courses:
            for c in courses:
                if not c.code:
                    continue
                skills = englishize_skills(c.skills or [])
                if skills:
                    course_skills[c.code.upper()] = skills
            if course_skills:
                profile.skills = englishize_skills((profile.skills or []) + [s for v in course_skills.values() for s in v])
            # sanitize courses on profile: keep only code
            profile.courses = [type(c)(code=c.code, name=None, topics=[], skills=[], tools=[]) for c in (profile.courses or [])]

    # Final englishize/filter skills and update normalized list + post-processing
    profile.skills = canonicalize_skill_list(englishize_skills(profile.skills or []))
    try:
        normalize_contact_location(profile, base_text=payload.free_text or "")
        normalize_education(profile, base_text=payload.free_text or "")
        normalize_experience_projects(profile)
    except Exception:
        pass
    normalized_skills = profile.skills

    # Normalize education from free_text
    base_text = (payload.free_text or "").lower()
    if "unsw" in base_text or "新南威尔" in base_text:
        for edu in (profile.education or []):
            if edu.school and ("unsw" in edu.school.lower() or "新南威尔" in edu.school):
                edu.school = "University of New South Wales"
    if any(x in base_text for x in ["master", "硕士", "研究生"]):
        for edu in (profile.education or []):
            if not edu.degree:
                edu.degree = "Master's"

    role_recommendations = recommend_roles_for_profile(profile, normalized_skills)

    return AnalyzeProfileOutput(
        profile=profile,
        normalized_skills=normalized_skills,
        course_enrichment_notes=notes,
        keywords=normalized_skills,
        course_skills=course_skills,
        role_recommendations=role_recommendations,
    )
