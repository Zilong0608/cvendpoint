from .schemas import RenderInput, RenderOutput
from modules.matching.schemas import MatchInput
from modules.matching.engine import match as run_match
from .refiner import refine_profile_with_llm


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _list(items):
    if not items:
        return "<ul></ul>"
    lis = "\n".join([f"<li>{_escape(i)}</li>" for i in items if i])
    return f"<ul>\n{lis}\n</ul>"


def _format_period(start: str | None, end: str | None) -> str:
    parts = []
    if start:
        parts.append(start)
    if end:
        parts.append(end)
    return " - ".join(parts)


def render_html(input: RenderInput) -> RenderOutput:
    profile = input.profile
    jd = input.jd

    # Optional LLM-based refinement (disabled in preserve mode)
    refine_notes = []
    refined_summary = None
    if input.polish and not getattr(input, 'preserve', False):
        try:
            refined_profile, refined_summary, notes = refine_profile_with_llm(profile, jd)
            profile = refined_profile or profile
            refine_notes = notes or []
        except Exception:
            pass

    name = _escape(getattr(profile, "name", None) or "Your Name")
    contact = _escape(getattr(profile, "contact", None) or "")
    location = _escape(getattr(profile, "location", None) or "")

    # Skills
    skills = [s for s in (profile.skills or []) if s]
    jd_keywords = [k.lower() for k in (jd.keywords if jd else [])]
    matched_skills = [s for s in skills if s.lower() in jd_keywords]
    unmatched_skills = [s for s in skills if s.lower() not in jd_keywords]

    # Experience bullets (prioritise JD keywords when polishing)
    exp_sections = []
    for exp in (profile.experience or []):
        bullets = exp.bullets or []
        if getattr(input, 'preserve', False):
            ordered_bullets = bullets
        else:
            hits = []
            rest = []
            for b in bullets:
                bl = (b or "").lower()
                if any(k in bl for k in jd_keywords):
                    hits.append(b)
                else:
                    rest.append(b)
            ordered_bullets = hits + rest
        exp_sections.append({
            "company": getattr(exp, "company", ""),
            "role": getattr(exp, "role", ""),
            "start": getattr(exp, "start", ""),
            "end": getattr(exp, "end", ""),
            "bullets": ordered_bullets,
        })

    # Education
    edu_sections = []
    for edu in (profile.education or []):
        edu_sections.append({
            "school": getattr(edu, "school", ""),
            "degree": getattr(edu, "degree", ""),
            "major": getattr(edu, "major", ""),
            "start": getattr(edu, "start", ""),
            "end": getattr(edu, "end", ""),
        })

    # Optional: compute match if JD provided
    match_result = None
    if jd is not None:
        try:
            mi = MatchInput(profile=profile, jd=jd)
            match_result = run_match(mi)
        except Exception:
            match_result = None

    # Summary text
    def collect_highlights(max_items: int = 2) -> list[str]:
        highlights: list[str] = []
        jd_terms = set((jd.keywords or [])) if jd else set()
        lower_terms = {t.lower() for t in jd_terms}

        for exp in profile.experience or []:
            if not exp.bullets:
                continue
            preferred = None
            for bullet in exp.bullets:
                if any(term in (bullet or "").lower() for term in lower_terms):
                    preferred = bullet
                    break
            if not preferred:
                preferred = exp.bullets[0]
            role = exp.role or "经历"
            company = exp.company or ""
            prefix = " @ ".join(filter(None, [role, company]))
            highlights.append(f"{prefix}：{preferred}")
            if len(highlights) >= max_items:
                break
        return highlights

    highlights = collect_highlights()

    base_summary = (getattr(profile, "summary", None) or "").strip()
    job_summary = ""

    if getattr(input, 'preserve', False):
        if jd is None:
            job_summary = "概要聚焦现有技能与经历，突出跨学科协作与交付能力。"
        else:
            job_title = getattr(jd, "title", None) or "目标岗位"
            mk = ", ".join(matched_skills[:4]) if matched_skills else None
            highlight_text = f" 亮点案例：{'；'.join(highlights)}。" if highlights else ""
            job_summary = f"针对 {job_title} 的精简概要，强化{(' ' + mk + ' 等核心技能') if mk else ' 岗位匹配度'}。{highlight_text}"
    else:
        if jd is None:
            general_skills = ", ".join(profile.skills[:6]) if profile.skills else "工程实践"
            highlight_text = f" 代表项目：{'；'.join(highlights)}。" if highlights else ""
            job_summary = f"具备 {general_skills} 相关经验，能够在快速节奏中完成端到端交付。{highlight_text}"
        else:
            job_title = getattr(jd, "title", None) or "目标岗位"
            company = getattr(jd, "company", None)
            head = f"针对 {job_title}" + (f"（{company}）" if company and company not in job_title else "")
            skill_clause = (
                f"强化 {', '.join(matched_skills[:5])}{'…' if len(matched_skills)>5 else ''} 等技能"
                if matched_skills
                else "突出岗位所需能力"
            )
            highlight_text = f" 代表项目：{'；'.join(highlights)}。" if highlights else ""
            job_summary = f"{head} 的定制概述：{skill_clause}，并结合实践经验呈现落地成效。{highlight_text}"

    summary = job_summary
    if base_summary:
        summary = base_summary if not job_summary else f"{base_summary} {job_summary}".strip()

    # If refiner produced a summary, prefer it
    if refined_summary:
        summary = refined_summary

    # Build HTML with required order
    html_parts = [
        "<html><head><meta charset='utf-8'>",
        "<style>@page{margin:18mm}body{font-family:'Segoe UI',Arial,sans-serif;font-size:12px;color:#f4f7ff;line-height:1.5;background:#0b1428;}h1{font-size:22px;margin:0;color:#ffffff;}h2{font-size:14px;margin:16px 0 6px;border-bottom:1px solid rgba(255,255,255,0.28);padding-bottom:4px;color:#7ec8ff;}h3{font-size:13px;margin:10px 0 4px;color:#d9e6ff;}ul{margin:6px 0 0 18px;padding:0}li{margin:2px 0}p{margin:6px 0;color:#e8efff;}section{margin-bottom:8px}</style>",
        "</head><body>",
        f"<h1>{name}</h1>",
        f"<p>{contact}{(' | ' + location) if location else ''}</p>",
        "<h2>个人简介</h2>",
        f"<p>{_escape(summary)}</p>",
    ]

    html_parts.append("<h2>教育背景</h2>")
    if edu_sections:
        for edu in edu_sections:
            school = _escape(edu["school"])
            degree_major = " · ".join(filter(None, [_escape(edu["degree"]), _escape(edu["major"])]))
            period = _format_period(edu["start"], edu["end"])
            line = f"{school}"
            if degree_major:
                line += f" · {degree_major}"
            if period:
                line += f" （{_escape(period)}）"
            html_parts.append(f"<p>{line}</p>")
    else:
        html_parts.append("<p>（待补充）</p>")

    html_parts.append("<h2>工作经历</h2>")
    if exp_sections:
        for sec in exp_sections:
            comp = _escape(sec.get("company") or "")
            role = _escape(sec.get("role") or "")
            period = _format_period(sec.get("start"), sec.get("end"))
            title_line = " · ".join(filter(None, [role, comp]))
            if period:
                title_line += f" （{_escape(period)}）"
            html_parts.append(f"<h3>{title_line}</h3>")
            html_parts.append(_list(sec.get("bullets") or []))
    else:
        html_parts.append("<p>（待补充）</p>")

    html_parts.append("<h2>技能</h2>")
    ordered_skills = matched_skills + unmatched_skills if not getattr(input, 'preserve', False) else skills
    html_parts.append(_list(ordered_skills))

    html_parts.append("</body></html>")
    html = "".join(html_parts)

    meta = {
        "template": input.template_id,
        "language": input.language,
        "polished": bool(input.polish),
        "preserve": bool(getattr(input, 'preserve', False)),
    }
    if match_result:
        meta["match"] = {"score": match_result.score}
    if refine_notes:
        meta["polish_notes"] = refine_notes
    return RenderOutput(html=html, meta=meta)
