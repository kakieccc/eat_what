from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import ContainerDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency
from app.modules.decision.schemas import DecisionRunResponse
from app.modules.history.schemas import HistoryPage

router = APIRouter(prefix="/discovery-sessions", tags=["discovery-sessions"])


@router.get("", responses=error_responses(400, 401, 422, 503))
async def list_discovery_sessions(
    services: ContainerDependency,
    user: CurrentUserDependency,
    cursor: str | None = None,
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
