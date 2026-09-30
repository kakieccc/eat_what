from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.auth.service import AuthService
from app.modules.choice.service import ChoiceService
from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.service.commands import DecisionCommandService
from app.modules.decision.service.queries import DecisionQueryService
from app.modules.decision.service.streaming import DecisionStreamService
from app.modules.history.service import HistoryService
from app.modules.location.service import LocationService
from app.modules.places.ports import GeoPlaceProvider
from app.modules.places.service import PlaceService
from app.modules.preferences.service import PreferencesService
from app.modules.task.service import TaskWorker


@dataclass
class Container:
    auth: AuthService
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    amap: GeoPlaceProvider
    llm: FoodDecisionLlm
    worker: TaskWorker
    decision_commands: DecisionCommandService
    decision_queries: DecisionQueryService
    decision_streams: DecisionStreamService
    location: LocationService
    places: PlaceService
    preferences: PreferencesService
    history: HistoryService
    choices: ChoiceService
