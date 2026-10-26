from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.middleware import register_middlewares
from app.api.router import router
from app.bootstrap import lifespan
from app.core.config import Settings


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="今天吃什么", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    register_middlewares(app, settings)
    register_exception_handlers(app)
    app.include_router(router)
    return app

app = create_app()
