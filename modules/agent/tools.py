from typing import List, Dict, Optional
import json
from modules.shared.config import (
    GPT_API_KEY,
    OPENAI_MODEL_WEB,
    OPENAI_USE_WEB_TOOL,
    OPENAI_WEB_TOOL_TYPE,
)
from modules.shared.logging import get_logger

logger = get_logger("agent.tools")


def web_search(query: str, top_k: int = 20, region: str = "AU") -> Optional[List[Dict]]:
    """
    Web search via GPT API (placeholder).

    Expected return format (list of dicts):
    [
      {"title": str, "url": str, "snippet": str, "company": str?, "location": str?, "posted_at": str?}
    ]

    Notes:
    - Implement by integrating your GPT web-enabled model or an external search API.
    - This placeholder returns None if GPT_API_KEY is not configured.
    """
    if not GPT_API_KEY:
        logger.warning("GPT_API_KEY not set; web_search returns empty list.")
        return []

    # Try OpenAI Responses API with web tool if enabled
    if OPENAI_USE_WEB_TOOL == "1":
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=GPT_API_KEY)
            system = (
                "You are a web job search assistant. Only return verifiable job listings. "
                "Target region: AU. Respond strictly in JSON array with objects: "
                "title, url, snippet, company(optional), location(optional), posted_at(optional)."
            )
            user = (
                f"Search for AU job listings using web search. Query: {query}. "
                f"Return top {top_k} unique results from reputable job pages."
            )
            # Use correct web tool type, e.g. 'web_search_preview' or 'web_search_preview_2025_03_11'
            tool_type = OPENAI_WEB_TOOL_TYPE or "web_search_preview"
            resp = client.responses.create(
                model=OPENAI_MODEL_WEB,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[{"type": tool_type}],  # requires org access to specific Web tool
            )

            # Best-effort: try to parse JSON from text output
            content = getattr(resp, "output_text", None) or getattr(resp, "content", None)
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        return data[:top_k]
                except Exception:
                    pass
            # If Responses returns structured tool output, try to read from 'output' or 'tools'
            try:
                chunks = getattr(resp, "output", None) or []
                for ch in chunks:
                    text = getattr(ch, "content", None)
                    if isinstance(text, list) and text:
                        parts = []
                        for t in text:
                            if isinstance(t, dict):
                                # Prefer explicit JSON content if provided
                                if t.get("type") == "output_text":
                                    parts.append(t.get("text", {}).get("value", ""))
                                else:
                                    parts.append(t.get("text", {}).get("value", ""))
                        s = "".join(parts)
                        if s:
                            data = json.loads(s)
                            if isinstance(data, list):
                                return data[:top_k]
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"OpenAI web tool path failed: {e}")

    # Fallback: return empty list (no fabrication)
    logger.info("web_search fallback: returning empty list (no web tool)")
    return []
