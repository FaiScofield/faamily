from fastapi import FastAPI

from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Family Butler API", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
