from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.history.service import HistoryService


def get_history_service(services: ContainerDependency) -> HistoryService:
    return services.history


HistoryServiceDependency = Annotated[HistoryService, Depends(get_history_service)]
