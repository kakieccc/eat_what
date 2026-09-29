from fastapi import APIRouter, Request
from sqlalchemy import text

from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope
from app.core.errors import AppError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> Envelope[dict[str, bool]]:
    return Envelope(data={"live": True})


@router.get("/ready", responses=error_responses(503))
async def ready(request: Request) -> Envelope[dict[str, bool]]:
    if not getattr(request.app.state, "ready", False):
        raise AppError("DEPENDENCY_UNAVAILABLE", "数据库或工作流尚未就绪", 503, True)
    async with request.app.state.container.sessions() as db:
        await db.execute(text("SELECT 1"))
    return Envelope(data={"ready": True})
