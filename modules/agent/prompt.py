from pathlib import Path
from typing import Dict


def load_system_prompt(context: Dict[str, str] | None = None) -> str:
    ctx = context or {}
    path = Path("prompts/system_prompt.txt")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    # lightweight variable injection
    for k, v in ctx.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

