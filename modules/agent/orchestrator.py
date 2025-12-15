from modules.profile.schemas import AnalyzeProfileInput
from modules.profile.service import analyze_profile
from .prompt import load_system_prompt


def run_end_to_end(payload: AnalyzeProfileInput):
    # Placeholder orchestrator with system prompt loading
    system_prompt = load_system_prompt({
        "DEFAULT_REGION": "AU",
        "OUTPUT_FORMAT_PRIMARY": "DOCX",
    })
    analyzed = analyze_profile(payload)
    return {
        "profile": analyzed.profile.dict(),
        "status": "ok",
        "system_prompt_loaded": bool(system_prompt.strip()),
    }
