from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.places.service import PlaceService


def get_place_service(services: ContainerDependency) -> PlaceService:
    return services.places


PlaceServiceDependency = Annotated[PlaceService, Depends(get_place_service)]
