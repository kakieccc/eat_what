from fastapi import APIRouter

from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency, MutationUserDependency
from app.modules.preferences.dependencies import PreferencesServiceDependency
from app.modules.preferences.schemas import Preferences, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", responses=error_responses(401, 503))
async def get_preferences(
    preferences: PreferencesServiceDependency,
    user: CurrentUserDependency,
) -> Envelope[Preferences]:
    return Envelope(data=await preferences.get(user.user.id))


@router.put("", responses=error_responses(401, 403, 422, 503))
async def replace_preferences(
    body: PreferencesUpdate,
    preferences: PreferencesServiceDependency,
    user: MutationUserDependency,
) -> Envelope[Preferences]:
    return Envelope(data=await preferences.save(user.user.id, body))
