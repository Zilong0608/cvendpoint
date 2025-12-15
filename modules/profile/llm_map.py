from __future__ import annotations

import json
from typing import Tuple, List

from modules.profile.schemas import Profile
from modules.shared.config import GPT_API_KEY, OPENAI_MODEL_PROFILE_EXTRACT
from modules.shared.logging import get_logger

logger = get_logger("profile.llm_map")


SYSTEM = (
    "You map resume content into structured fields without rewriting bullets. "
    "RULES: Do not fabricate; keep original text for bullets and project lines. "
    "Fill degree, major, start, end, company, role when clearly present. "
    "Return compact JSON only with key 'profile' (same schema)."
)


def strict_map_profile(profile: Profile, *, timeout: float = 45.0, model: str | None = None) -> Tuple[Profile, List[str]]:
    if not GPT_API_KEY:
        return profile, ["llm_map_unavailable:no_key"]

    mdl = model or OPENAI_MODEL_PROFILE_EXTRACT or "gpt-4o-mini"
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=GPT_API_KEY)

        user = (
            "Map the following profile to structured fields. Keep bullets unchanged.\n"
            + json.dumps(profile.model_dump(), ensure_ascii=False)
            + "\nOutput JSON: {\"profile\": <mapped-profile>}"
        )
        # Prefer Responses API
        try:
            resp = client.responses.create(
                model=mdl,
                input=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
                timeout=timeout,
            )
            text = getattr(resp, "output_text", None) or getattr(resp, "content", "") or ""
        except Exception as e:
            logger.info(f"Responses API failed ({type(e).__name__}); trying chat.completions")
            chat = client.chat.completions.create(
                model=mdl,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=1,
                timeout=timeout,
            )
            text = chat.choices[0].message.content or ""

        s = text.strip()
        if s.startswith("```"):
            s = "\n".join(s.splitlines()[1:])
            if s.endswith("```"):
                s = "\n".join(s.splitlines()[:-1])
        data = json.loads(s)
        prof_dict = data.get("profile") or {}
        if not isinstance(prof_dict, dict):
            return profile, ["llm_map_bad_output"]
        mapped = Profile(**{**profile.model_dump(), **prof_dict})
        return mapped, ["llm_map_ok"]
    except Exception as e:
        logger.warning(f"LLM strict map failed: {e}")
        return profile, [f"llm_map_error:{type(e).__name__}"]

