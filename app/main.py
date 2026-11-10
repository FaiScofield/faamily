from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.admin import router as admin_router
from app.api.announcements import router as announcements_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.families import router as families_router
from app.api.scenarios import router as scenarios_router
from app.api.tasks import router as tasks_router
from app.api.vip import router as vip_router
from app.core.config import settings


def _get_client_ip(request: Request) -> str:
    """Extract client IP for rate limiting.

    ``X-Forwarded-For`` is only honoured when ``TRUSTED_PROXY_HOPS`` is set,
    because the header is trivially spoofable. Without a trusted proxy in
    front, an attacker could rotate the header to dodge the rate limiter.
    """
    hops = settings.trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if len(parts) >= hops:
                # Rightmost entry is appended by the closest proxy.
                return parts[-hops]
    return get_remote_address(request)


limiter = Limiter(key_func=_get_client_ip)


def _cors_origins() -> list[str]:
    """Parse the comma-separated CORS origin allowlist."""
    raw = (settings.cors_origins or "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family Butler API",
        version="0.7.0",
        description="Backend API for the Family Butler WeChat Mini Program",
    )

    app.state.limiter = limiter

    # CORS: only enabled when an explicit allowlist is configured. The
    # Nginx deployment serves the web UI and the API from one origin, so the
    # default (empty) works without any CORS headers at all.
    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
    app.include_router(vip_router, prefix="/v1")
    app.include_router(admin_router, prefix="/v1")

    return app


app = create_app()
