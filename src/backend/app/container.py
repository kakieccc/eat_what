from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.service import AuthService
from app.modules.choice.service import ChoiceService
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.history.service import HistoryService
from app.modules.location.ports import LocationProvider
from app.modules.places.service import PlaceService
from app.modules.preferences.ports import PreferencesRepository
from app.modules.task.service import TaskWorker


@dataclass
class Container:
    auth: AuthService
    sessions: async_sessionmaker[AsyncSession]
    worker: TaskWorker
    decision_commands: DecisionCommandService
    decision_queries: DecisionQueryService
    decision_streams: DecisionStreamService
    location: LocationProvider
    places: PlaceService
    preferences: PreferencesRepository
    history: HistoryService
    choices: ChoiceService
