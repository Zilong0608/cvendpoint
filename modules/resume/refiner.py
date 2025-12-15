import json
from typing import Optional

from modules.profile.schemas import Profile
from modules.jd.schemas import ParsedJD
from modules.shared.config import GPT_API_KEY, OPENAI_MODEL_REFINE
from modules.shared.logging import get_logger

logger = get_logger("resume.refiner")


SYSTEM = (
    "You rewrite resume content for clarity, impact, and ATS-friendliness. "
    "RULES: Do not fabricate facts, companies, dates, or metrics. "
    "Preserve truthfulness. You may rephrase, reorder, and condense. "
    "Prefer action-impact bullets (Strong verb -> what -> measurable impact when provided). "
    "If no numbers are provided, do not invent them. Keep qualitative claims. "
    "Align language to provided JD keywords if present (synonyms allowed)."
)


def _build_user_prompt(profile: Profile, jd: Optional[ParsedJD], tone: str, tense: str, max_bullets_per_role: int, include_jd_keywords: bool) -> str:
    data = {
        "profile": profile.model_dump(),
        "jd_keywords": (jd.keywords if (jd and include_jd_keywords) else []),
        "jd_requirements": (jd.requirements if jd else []),
        "constraints": {
            "tone": tone,
            "tense": tense,
            "max_bullets_per_role": max_bullets_per_role,
        },
        "output_format": {
            "summary": "1-2 sentences, tailored to JD if present",
            "experience": "rewrite bullets per role, max bullets as requested",
        },
    }
    return (
        "Rewrite the resume content according to constraints and output a JSON with keys: "
        "{\"summary\": string, \"profile\": profile-object-with-rewritten-bullets}.\n"
        f"INPUT:\n{json.dumps(data, ensure_ascii=False)}"
    )


def refine_profile_with_llm(profile: Profile, jd: Optional[ParsedJD], *, tone: str = "impactful", tense: str = "past", max_bullets_per_role: int = 5, include_jd_keywords: bool = True):
    if not GPT_API_KEY:
        logger.warning("GPT_API_KEY not set; skipping LLM refinement.")
        return profile, None, ["llm_unavailable"]

    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=GPT_API_KEY)

        user = _build_user_prompt(profile, jd, tone, tense, max_bullets_per_role, include_jd_keywords)

        # Prefer Responses API for broader model support
        try:
            resp = client.responses.create(
                model=OPENAI_MODEL_REFINE,
                input=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user + "\nOutput JSON only, no markdown, no commentary."},
                ],
            )
            text = getattr(resp, "output_text", None) or getattr(resp, "content", "") or ""
        except Exception as e:
            logger.info(f"Responses API failed ({type(e).__name__}), trying chat.completions")
            chat = client.chat.completions.create(
                model=OPENAI_MODEL_REFINE,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user + "\nOutput JSON only, no markdown, no commentary."},
                ],
                temperature=0.2,
            )
            text = chat.choices[0].message.content or ""

        # Try to strip code fences if present and parse
        text_stripped = text.strip()
        if text_stripped.startswith("```"):
            # remove the first fence and possible language token
            text_stripped = "\n".join(text_stripped.splitlines()[1:])
            if text_stripped.endswith("```"):
                text_stripped = "\n".join(text_stripped.splitlines()[:-1])

        data = json.loads(text_stripped)
        out_profile = Profile(**data.get("profile", profile.model_dump()))
        summary = data.get("summary")
        return out_profile, summary, ["ok"]
    except Exception as e:
        logger.warning(f"LLM refine failed: {e}")
        return profile, None, [f"llm_error:{type(e).__name__}"]
