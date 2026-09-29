from fastapi import APIRouter, Query

from app.api.dependencies import ContainerDependency, CurrentUserDependency
from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope
from app.application.decision.models import DecisionRunResponse
from app.domain.history.models import HistoryPage

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
    session_id: str,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[list[DecisionRunResponse]]:
    run_ids = await services.history.runs(user.user.id, session_id)
    return Envelope(data=[
        await services.decision_queries.get_for_user(user.user.id, run_id)
        for run_id in run_ids
    ])
