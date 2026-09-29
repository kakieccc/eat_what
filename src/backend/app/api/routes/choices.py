from fastapi import APIRouter

from app.api.dependencies import ContainerDependency, IdempotencyDependency, MutationUserDependency
from app.api.errors.responses import error_responses
from app.api.schemas.choices import PlaceChoiceRequest
from app.api.schemas.common import Envelope

router = APIRouter(prefix="/place-choices", tags=["place-choices"])


@router.post("", status_code=201, responses=error_responses(401, 403, 404, 409, 422, 503))
async def create_place_choice(
    body: PlaceChoiceRequest,
    services: ContainerDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[dict[str, str]]:
    result = await services.choices.choose(
        user.user.id,
        body.candidate_id,
        body.feedback,
        idempotency_key,
    )
    return Envelope(data=result)
