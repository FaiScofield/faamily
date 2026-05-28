from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.announcements import router as announcements_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.families import router as families_router
from app.api.scenarios import router as scenarios_router
from app.api.tasks import router as tasks_router
from app.core.config import settings


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, supporting proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Initialize rate limiter
limiter = Limiter(key_func=_get_client_ip)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family Butler API",
        version="0.6.0",
        description="Backend API for the Family Butler WeChat Mini Program",
    )

    # Attach rate limiter state to app
    app.state.limiter = limiter

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.app_env}

    # Register API routers
    app.include_router(auth_router, prefix="/v1")
    app.include_router(families_router, prefix="/v1")
    app.include_router(tasks_router, prefix="/v1")
    app.include_router(announcements_router, prefix="/v1")
    app.include_router(documents_router, prefix="/v1")
    app.include_router(scenarios_router, prefix="/v1")

    return app


app = create_app()
