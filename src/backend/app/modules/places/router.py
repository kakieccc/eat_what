from typing import Annotated, get_args

from fastapi import APIRouter, Query
from pydantic import AfterValidator

from app.api.dependencies import ContainerDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.modules.auth.dependencies import CurrentUserDependency
from app.modules.location.schemas import Origin
from app.modules.places.schemas import Place
from app.modules.preferences.rules import require_supported_radius
from app.modules.preferences.schemas import SearchRadius

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", responses=error_responses(401, 422, 502, 503))
async def list_places(
    services: ContainerDependency,
    user: CurrentUserDependency,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    address: Annotated[str, Query(max_length=200)] = "",
    radius_meters: Annotated[
        int,
        Query(alias="radiusMeters", json_schema_extra={"enum": list(get_args(SearchRadius))}),
        AfterValidator(require_supported_radius),
    ] = 2000,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    keywords: Annotated[list[str] | None, Query(max_length=5)] = None,
) -> Envelope[list[Place]]:
    normalized = list(dict.fromkeys(word.strip() for word in keywords or [] if word.strip()))
    result = await services.places.search(
        Origin(latitude=latitude, longitude=longitude, address=address),
        radius_meters,
        limit,
        normalized,
    )
    return Envelope(data=result.places)


@router.get("/{place_key}", responses=error_responses(401, 404, 422, 503))
async def get_place(
    place_key: str,
    services: ContainerDependency,
    user: CurrentUserDependency,
) -> Envelope[Place]:
    return Envelope(data=await services.places.read(user.user.id, place_key))
