from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family Butler API",
        version="0.2.0",
        description="Backend API for the Family Butler WeChat Mini Program",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.app_env}

    # Register API routers
    app.include_router(auth_router, prefix="/v1")

    return app


app = create_app()
