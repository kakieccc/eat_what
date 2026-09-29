from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import ContainerDependency, CurrentUserDependency
from app.api.errors.responses import error_responses
from app.api.schemas.common import Envelope
from app.domain.geo.models import Origin
from app.domain.places.models import Place

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", responses=error_responses(401, 422, 502, 503))
async def list_places(
    services: ContainerDependency,
    user: CurrentUserDependency,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    address: Annotated[str, Query(max_length=200)] = "",
    radius_meters: Annotated[int, Query(alias="radiusMeters", ge=100, le=50000)] = 2000,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    keywords: Annotated[list[str] | None, Query(max_length=5)] = None,
) -> Envelope[list[Place]]:
    places = await services.places.search(
        Origin(latitude=latitude, longitude=longitude, address=address),
        radius_meters,
        limit,
        keywords or [],
    )
    return Envelope(data=places)


@router.get("/{place_key}", responses=error_responses(401, 404, 422, 502, 503))
async def get_place(
    place_key: str,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[Place]:
    return Envelope(data=await services.places.read(user.user.id, place_key))
