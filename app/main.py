from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CV_ROOT = Path(__file__).resolve().parents[2] / "cv"
if CV_ROOT.exists():
    sys.path.insert(0, str(CV_ROOT))

from modules.profile.router import router as profile_router
from modules.jobs.router import router as jobs_router
from modules.jd.router import router as jd_router
from modules.matching.router import router as matching_router
from modules.resume.router import router as resume_router


def create_app() -> FastAPI:
    app = FastAPI(title="CV Endpoint Service", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(profile_router, prefix="/profile", tags=["profile"])
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
    app.include_router(jd_router, prefix="/jd", tags=["jd"])
    app.include_router(matching_router, prefix="/matching", tags=["matching"])
    app.include_router(resume_router, prefix="/resume", tags=["resume"])

    @app.get("/health", tags=["meta"], summary="Service health check")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()