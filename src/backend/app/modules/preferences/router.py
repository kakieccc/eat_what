from fastapi import APIRouter

from app.api.dependencies import ContainerDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency, MutationUserDependency
from app.modules.preferences.schemas import PreferencesResponse, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", responses=error_responses(401, 503))
async def get_preferences(
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[PreferencesResponse]:
    return Envelope(data=await services.preferences.get(user.user.id))


@router.put("", responses=error_responses(401, 403, 409, 422, 503))
async def replace_preferences(
    body: PreferencesUpdate,
    services: ContainerDependency,
    user: MutationUserDependency,
) -> Envelope[PreferencesResponse]:
    return Envelope(data=await services.preferences.save(user.user.id, body))
