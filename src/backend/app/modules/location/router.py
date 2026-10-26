from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import ContainerDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency
from app.modules.location.schemas import Origin, Point

router = APIRouter(tags=["locations"])


@router.get("/resolved-locations", responses=error_responses(401, 422, 502, 503))
async def resolve_location(
    services: ContainerDependency,
    user: CurrentUserDependency,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
) -> Envelope[Origin]:
    return Envelope(
        data=await services.location.reverse(Point(latitude=latitude, longitude=longitude))
    )


@router.get("/location-suggestions", responses=error_responses(401, 422, 502, 503))
async def list_location_suggestions(
    services: ContainerDependency,
    user: CurrentUserDependency,
    query: Annotated[str, Query(min_length=2, max_length=100)],
) -> Envelope[list[Origin]]:
    return Envelope(data=await services.location.tips(query))
