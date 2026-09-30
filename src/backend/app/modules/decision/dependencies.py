from typing import Annotated

from fastapi import Depends

from app.api.dependencies import ContainerDependency
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.streaming import DecisionStreamService


def get_decision_commands(services: ContainerDependency) -> DecisionCommandService:
    return services.decision_commands


def get_decision_queries(services: ContainerDependency) -> DecisionQueryService:
    return services.decision_queries


def get_decision_streams(services: ContainerDependency) -> DecisionStreamService:
    return services.decision_streams


DecisionCommandsDependency = Annotated[DecisionCommandService, Depends(get_decision_commands)]
DecisionQueriesDependency = Annotated[DecisionQueryService, Depends(get_decision_queries)]
DecisionStreamsDependency = Annotated[DecisionStreamService, Depends(get_decision_streams)]
