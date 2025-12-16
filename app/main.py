from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import modules directly - they are now in the project root
from modules.profile.router import router as profile_router
from modules.jobs.router import router as jobs_router
from modules.jd.router import router as jd_router
from modules.matching.router import router as matching_router
from modules.resume.router import router as resume_router

# Import Supabase client
from modules.shared.database import supabase

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="CV Endpoint Service", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include all routers
    app.include_router(profile_router, prefix="/profile", tags=["profile"])
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
    app.include_router(jd_router, prefix="/jd", tags=["jd"])
    app.include_router(matching_router, prefix="/matching", tags=["matching"])
    app.include_router(resume_router, prefix="/resume", tags=["resume"])

    @app.get("/", include_in_schema=False)
    async def root():
        """Serve the frontend HTML page"""
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "CV Endpoint Service", "docs": "/docs"}

    @app.get("/health", tags=["meta"], summary="Service health check")
    async def health():
        db_status = "disconnected"
        if supabase:
            try:
                # 尝试连接数据库
                supabase.table("uni_course1").select("*", count="exact").limit(1).execute()
                db_status = "connected"
            except Exception as e:
                db_status = f"error: {str(e)}"
        
        return {
            "status": "ok",
            "database": db_status
        }
    
    @app.get("/courses", tags=["database"], summary="Get courses from database")
    async def get_courses(limit: int = 10):
        """
        从 uni_course1 表中获取课程数据
        """
        if not supabase:
            return {"error": "数据库未连接"}
        
        try:
            response = supabase.table("uni_course1").select("*").limit(limit).execute()
            return {
                "success": True,
                "count": len(response.data),
                "data": response.data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # Mount static files (CSS, JS) - must be after routes
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()