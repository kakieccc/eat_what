from fastapi import APIRouter

from app.api.dependencies import ContainerDependency, CurrentUserDependency, MutationUserDependency
from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope
from app.domain.preferences.models import Preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", responses=error_responses(401, 503))
async def get_preferences(
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[Preferences]:
    return Envelope(data=await services.preferences.get(user.user.id))


@router.put("", responses=error_responses(401, 403, 422, 503))
async def replace_preferences(
    body: Preferences,
    services: ContainerDependency,
    user: MutationUserDependency,
) -> Envelope[Preferences]:
    return Envelope(data=await services.preferences.save(user.user.id, body))
