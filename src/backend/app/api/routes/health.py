from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import SessionsDependency
from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> Envelope[dict[str, bool]]:
    return Envelope(data={"live": True})


@router.get("/ready", responses=error_responses(503))
async def ready(sessions: SessionsDependency) -> Envelope[dict[str, bool]]:
    async with sessions() as db:
        await db.execute(text("SELECT 1"))
    return Envelope(data={"ready": True})
