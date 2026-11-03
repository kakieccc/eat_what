import base64
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, TypeAdapter

from app.api.dependencies import ContainerDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.core.errors import AppError
from app.modules.auth.dependencies import CurrentUserDependency
from app.modules.decision.schemas import DecisionRunResponse
from app.modules.history.schemas import HistoryCursor, HistoryPage

router = APIRouter(prefix="/discovery-sessions", tags=["discovery-sessions"])
CURSOR_ADAPTER = TypeAdapter(tuple[AwareDatetime, UUID])


def parse_cursor(cursor: str | None = None) -> HistoryCursor | None:
    if cursor is None:
        return None
    try:
        if len(cursor) > 1024:
            raise ValueError
        timestamp, row_id = CURSOR_ADAPTER.validate_json(
            base64.b64decode(cursor, altchars=b"-_", validate=True), strict=True,
        )
    except (ValueError, TypeError, UnicodeError):
        raise AppError("INVALID_CURSOR", "分页参数无效") from None
    return timestamp, str(row_id)


@router.get("", responses=error_responses(400, 401, 422, 503))
async def list_discovery_sessions(
    services: ContainerDependency,
    user: CurrentUserDependency,
    cursor: Annotated[HistoryCursor | None, Depends(parse_cursor)],
    limit: int = Query(default=20, ge=1, le=50),
) -> Envelope[HistoryPage]:
    return Envelope(data=await services.history.list_sessions(user.user.id, cursor, limit))


@router.get("/{session_id}/decision-runs", responses=error_responses(401, 404, 422, 503))
async def list_session_decision_runs(
    session_id: UUID,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[list[DecisionRunResponse]]:
    return Envelope(data=await services.history.runs(user.user.id, str(session_id)))
