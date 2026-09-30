from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.location.service import LocationService


def get_location_service(services: ContainerDependency) -> LocationService:
    return services.location


LocationServiceDependency = Annotated[LocationService, Depends(get_location_service)]
