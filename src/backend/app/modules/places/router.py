from typing import Annotated

from fastapi import APIRouter, Query

from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency
from app.modules.location.schemas import Origin
from app.modules.places.dependencies import PlaceServiceDependency
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import SearchRadius

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", responses=error_responses(401, 422, 502, 503))
async def list_places(
    place_service: PlaceServiceDependency,
    user: CurrentUserDependency,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    address: Annotated[str, Query(max_length=200)] = "",
    radius_meters: Annotated[SearchRadius, Query(alias="radiusMeters")] = 2000,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    keywords: Annotated[list[str] | None, Query(max_length=5)] = None,
) -> Envelope[list[Place]]:
    places = await place_service.search(
        Origin(latitude=latitude, longitude=longitude, address=address),
        radius_meters,
        limit,
        keywords or [],
    )
    return Envelope(data=places)


@router.get("/{place_key}", responses=error_responses(401, 404, 422, 503))
async def get_place(
    place_key: str,
    place_service: PlaceServiceDependency,
    user: CurrentUserDependency,
) -> Envelope[Place]:
    return Envelope(data=await place_service.read(user.user.id, place_key))
