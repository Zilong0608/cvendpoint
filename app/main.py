from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CV_ROOT = Path(__file__).resolve().parents[2] / "cv"
if CV_ROOT.exists():
    sys.path.insert(0, str(CV_ROOT))

# Try to import modules - try multiple import paths
MODULES_AVAILABLE = False
MODULES_ERROR = None

# Try different import paths
import_attempts = [
    # Try 1: Direct import (if modules is at package root)
    ("from modules.profile.router import router as profile_router", "direct"),
    # Try 2: From cv_suite package (package name with underscore)
    ("from cv_suite.modules.profile.router import router as profile_router", "cv_suite.modules"),
    # Try 3: From cv-suite package (if package name allows hyphen)
    ("from cv_suite import modules; from modules.profile.router import router as profile_router", "cv_suite then modules"),
]

for import_stmt, method in import_attempts:
    try:
        # Try to find and add cv-suite to path first
        try:
            import pkg_resources
            dist = pkg_resources.get_distribution('cv-suite')
            if dist and dist.location:
                dist_path = Path(dist.location)
                # Add package location to path
                if dist_path not in sys.path:
                    sys.path.insert(0, str(dist_path))
                # Also check if there's a src directory
                src_path = dist_path / "src"
                if src_path.exists() and src_path not in sys.path:
                    sys.path.insert(0, str(src_path))
        except:
            pass
        
        # Now try the import
        if method == "direct":
            from modules.profile.router import router as profile_router
            from modules.jobs.router import router as jobs_router
            from modules.jd.router import router as jd_router
            from modules.matching.router import router as matching_router
            from modules.resume.router import router as resume_router
        elif method == "cv_suite.modules":
            from cv_suite.modules.profile.router import router as profile_router
            from cv_suite.modules.jobs.router import router as jobs_router
            from cv_suite.modules.jd.router import router as jd_router
            from cv_suite.modules.matching.router import router as matching_router
            from cv_suite.modules.resume.router import router as resume_router
        elif method == "cv_suite then modules":
            import cv_suite
            # Add cv_suite location to path
            cv_suite_path = Path(cv_suite.__file__).parent if hasattr(cv_suite, '__file__') else None
            if cv_suite_path:
                sys.path.insert(0, str(cv_suite_path))
            from modules.profile.router import router as profile_router
            from modules.jobs.router import router as jobs_router
            from modules.jd.router import router as jd_router
            from modules.matching.router import router as matching_router
            from modules.resume.router import router as resume_router
        
        MODULES_AVAILABLE = True
        MODULES_IMPORT_METHOD = method
        break
    except ImportError as e:
        MODULES_ERROR = f"{method}: {str(e)}"
        continue
    except Exception as e:
        MODULES_ERROR = f"{method}: {str(e)}"
        continue

if not MODULES_AVAILABLE:
    # Create dummy routers to prevent app crash
    from fastapi import APIRouter
    profile_router = jobs_router = jd_router = matching_router = resume_router = APIRouter()
    MODULES_IMPORT_METHOD = "none"


def create_app() -> FastAPI:
    app = FastAPI(title="CV Endpoint Service", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Only include routers if modules are available
    if MODULES_AVAILABLE:
        app.include_router(profile_router, prefix="/profile", tags=["profile"])
        app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
        app.include_router(jd_router, prefix="/jd", tags=["jd"])
        app.include_router(matching_router, prefix="/matching", tags=["matching"])
        app.include_router(resume_router, prefix="/resume", tags=["resume"])
    else:
        @app.get("/modules-error", tags=["meta"])
        async def modules_error():
            return {
                "error": "Modules not available",
                "details": MODULES_ERROR,
                "help": "Check /debug endpoint for more information"
            }

    @app.get("/health", tags=["meta"], summary="Service health check")
    async def health():
        return {"status": "ok"}

    @app.get("/debug", tags=["meta"], summary="Debug information")
    async def debug():
        """诊断信息，帮助排查 modules 导入问题"""
        import sys
        import site
        from pathlib import Path
        
        debug_info = {
            "python_path": sys.path,
            "site_packages": site.getsitepackages(),
            "current_file": str(Path(__file__).resolve()),
            "cv_root_exists": CV_ROOT.exists() if 'CV_ROOT' in globals() else False,
        }
        
        # 检查 cv-suite 是否安装
        try:
            import pkg_resources
            try:
                dist = pkg_resources.get_distribution('cv-suite')
                debug_info["cv_suite_installed"] = True
                debug_info["cv_suite_location"] = dist.location
                debug_info["cv_suite_version"] = dist.version
                
                # 检查 modules 是否存在
                dist_path = Path(dist.location)
                debug_info["modules_in_package"] = (dist_path / "modules").exists()
                debug_info["modules_in_parent"] = (dist_path.parent / "modules").exists()
            except pkg_resources.DistributionNotFound:
                debug_info["cv_suite_installed"] = False
                debug_info["cv_suite_error"] = "DistributionNotFound"
        except ImportError:
            debug_info["pkg_resources_available"] = False
        
        # 尝试查找 modules
        modules_found = []
        for path in sys.path:
            path_obj = Path(path)
            if (path_obj / "modules").exists():
                modules_found.append(str(path_obj / "modules"))
        debug_info["modules_found_at"] = modules_found
        
        # 尝试导入 modules
        try:
            import modules
            debug_info["modules_importable"] = True
            debug_info["modules_location"] = str(Path(modules.__file__).parent) if hasattr(modules, '__file__') else "unknown"
        except ImportError as e:
            debug_info["modules_importable"] = False
            debug_info["modules_import_error"] = str(e)
        
        # 添加当前模块状态
        debug_info["modules_available_in_app"] = MODULES_AVAILABLE
        if not MODULES_AVAILABLE:
            debug_info["modules_error_in_app"] = MODULES_ERROR
        else:
            debug_info["modules_import_method"] = MODULES_IMPORT_METHOD if 'MODULES_IMPORT_METHOD' in globals() else "unknown"
        
        # 尝试导入 cv_suite 看看结构
        try:
            import cv_suite
            debug_info["cv_suite_importable"] = True
            if hasattr(cv_suite, '__file__'):
                debug_info["cv_suite_file"] = str(Path(cv_suite.__file__).parent)
                # 列出 cv_suite 目录内容
                cv_suite_dir = Path(cv_suite.__file__).parent
                debug_info["cv_suite_contents"] = [str(p.name) for p in cv_suite_dir.iterdir() if p.is_dir() or p.suffix == '.py']
        except ImportError as e:
            debug_info["cv_suite_importable"] = False
            debug_info["cv_suite_import_error"] = str(e)
        
        return debug_info

    return app


app = create_app()