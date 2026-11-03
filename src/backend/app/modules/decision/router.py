from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from starlette.responses import StreamingResponse

from app.api.dependencies import ContainerDependency, IdempotencyDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency, MutationUserDependency
from app.modules.decision.schemas import (
    DecisionCreateRequest,
    DecisionRunResponse,
    RefinementRequest,
)
from app.modules.decision.sse import encode

router = APIRouter(prefix="/decision-runs", tags=["decision-runs"])


async def stream_connection(services: ContainerDependency, user: CurrentUserDependency) -> AsyncIterator[None]:
    async with services.decision_streams.connection(user.user.id):
        yield


@router.post("", status_code=201, responses=error_responses(401, 403, 409, 422, 429, 503))
async def create_decision_run(
    body: DecisionCreateRequest,
    request: Request,
    response: Response,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[DecisionRunResponse]:
    run_id = await services.decision_commands.create(
        user.user.id, body, idempotency_key, request.state.request_id
    )
    response.headers["Location"] = f"/decision-runs/{run_id}"
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, run_id))


@router.get("/{run_id}", responses=error_responses(401, 404, 409, 422, 503))
async def get_decision_run(
    run_id: UUID,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[DecisionRunResponse]:
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, str(run_id)))


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses=error_responses(401, 404, 409, 422, 429, 503),
)
async def stream_decision_run_events(
    run_id: UUID,
    request: Request,
    services: ContainerDependency,
    user: CurrentUserDependency,
    # Keep the slot until the response closes, including disconnects before the first event.
    _connection: Annotated[None, Depends(stream_connection, scope="request")],
) -> StreamingResponse:
    await services.decision_queries.stream_status(user.user.id, str(run_id))
    return StreamingResponse(
        encode(
            services.decision_streams.stream(
                user.user.id,
                str(run_id),
                request.cookies.get("food_session"),
            )
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{run_id}/refinements",
    status_code=201,
    responses=error_responses(400, 401, 403, 404, 409, 422, 429, 503),
)
async def create_decision_refinement(
    run_id: UUID,
    body: RefinementRequest,
    request: Request,
    response: Response,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[DecisionRunResponse]:
    child_id = await services.decision_commands.refine(
        user.user.id, str(run_id), body, idempotency_key, request.state.request_id
    )
    response.headers["Location"] = f"/decision-runs/{child_id}"
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, child_id))


@router.post("/{run_id}/retry", status_code=201, responses=error_responses(401, 403, 404, 409, 422, 429, 503))
async def retry_decision_run(
    run_id: UUID,
    request: Request,
    response: Response,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[DecisionRunResponse]:
    child_id = await services.decision_commands.retry(
        user.user.id, str(run_id), idempotency_key, request.state.request_id
    )
    response.headers["Location"] = f"/decision-runs/{child_id}"
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, child_id))
