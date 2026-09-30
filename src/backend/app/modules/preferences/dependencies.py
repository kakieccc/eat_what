from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.preferences.service import PreferencesService


def get_preferences_service(services: ContainerDependency) -> PreferencesService:
    return services.preferences


PreferencesServiceDependency = Annotated[PreferencesService, Depends(get_preferences_service)]
