from fastapi import APIRouter

from app.api.dependencies import IdempotencyDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import MutationUserDependency
from app.modules.choice.dependencies import ChoiceServiceDependency
from app.modules.choice.schemas import PlaceChoiceRequest

router = APIRouter(prefix="/place-choices", tags=["place-choices"])


@router.post("", status_code=200, responses=error_responses(401, 403, 404, 409, 422, 503))
async def create_place_choice(
    body: PlaceChoiceRequest,
    choices: ChoiceServiceDependency,
    user: MutationUserDependency,
    idempotency_key: IdempotencyDependency,
) -> Envelope[dict[str, str]]:
    result = await choices.choose(
        user.user.id,
        str(body.candidate_id),
        idempotency_key,
    )
    return Envelope(data=result)
