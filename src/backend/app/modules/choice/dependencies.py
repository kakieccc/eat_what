from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.choice.service import ChoiceService


def get_choice_service(services: ContainerDependency) -> ChoiceService:
    return services.choices


ChoiceServiceDependency = Annotated[ChoiceService, Depends(get_choice_service)]
