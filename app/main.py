from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.families import router as families_router
from app.api.tasks import router as tasks_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family Butler API",
        version="0.4.0",
        description="Backend API for the Family Butler WeChat Mini Program",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.app_env}

    # Register API routers
    app.include_router(auth_router, prefix="/v1")
    app.include_router(families_router, prefix="/v1")
    app.include_router(tasks_router, prefix="/v1")

    return app


app = create_app()
