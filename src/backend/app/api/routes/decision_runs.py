from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from starlette.responses import StreamingResponse

from app.api.dependencies import (
    ContainerDependency,
    CurrentUserDependency,
    IdempotencyDependency,
    MutationUserDependency,
)
from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope
from app.api.schemas.decisions import DecisionCreateRequest, DecisionRunUpdateRequest
from app.api.sse import encode
from app.application.decision.models import DecisionRunResponse, RefinementRequest
from app.core.errors import AppError

router = APIRouter(prefix="/decision-runs", tags=["decision-runs"])


async def wait_result(
    services: ContainerDependency, user_id: str, run_id: str
) -> DecisionRunResponse:
    deadline = asyncio.get_running_loop().time() + services.settings.decision_timeout_seconds + 5
    while True:
        result = await services.decision_queries.get_for_user(user_id, run_id)
        if result.status in {"completed", "awaitingConfirmation"}:
            return result
        if result.status == "failed":
            code = result.error_code or "RUN_FAILED"
            raise AppError(
                code,
                "推荐未完成，请检查服务或重试",
                504 if code == "DECISION_TIMEOUT" else 502,
                True,
            )
        if asyncio.get_running_loop().time() >= deadline:
            raise AppError("DECISION_TIMEOUT", "本次推荐超时，请稍后查询结果", 504, True)
        await asyncio.sleep(0.2)


@router.post("", status_code=201, responses=error_responses(401, 403, 409, 422, 503))
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
    response.headers["Location"] = f"/api/v2/decision-runs/{run_id}"
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, run_id))


@router.get("/{run_id}", responses=error_responses(401, 404, 422, 503))
async def get_decision_run(
    run_id: str,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[DecisionRunResponse]:
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, run_id))


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses=error_responses(401, 404, 422, 503),
)
async def stream_decision_run_events(
    run_id: str,
    request: Request,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> StreamingResponse:
    await services.decision_queries.get_for_user(user.user.id, run_id)
    return StreamingResponse(
        encode(services.decision_streams.stream(
            user.user.id, run_id, request.state.request_id,
            request.cookies.get("food_session"),
        )),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{run_id}/refinements",
    status_code=201,
    responses=error_responses(400, 401, 403, 404, 409, 422, 503),
)
async def create_decision_refinement(
    run_id: str,
    body: RefinementRequest,
    request: Request,
    response: Response,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[DecisionRunResponse]:
    child_id = await services.decision_commands.refine(
        user.user.id, run_id, body, idempotency_key, request.state.request_id
    )
    response.headers["Location"] = f"/api/v2/decision-runs/{child_id}"
    return Envelope(data=await services.decision_queries.get_for_user(user.user.id, child_id))


@router.patch(
    "/{run_id}", responses=error_responses(401, 403, 404, 409, 422, 502, 503, 504)
)
async def update_decision_run(
    run_id: str,
    body: DecisionRunUpdateRequest,
    request: Request,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[DecisionRunResponse]:
    await services.decision_commands.resume(
        user.user.id,
        run_id,
        body.accept_changes,
        idempotency_key,
        request.state.request_id,
    )
    return Envelope(data=await wait_result(services, user.user.id, run_id))
