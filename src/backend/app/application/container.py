from typing import Protocol

from app.application.auth.service import AuthService
from app.application.choice.ports import ChoiceRepository
from app.application.decision.commands import DecisionCommandService
from app.application.decision.queries import DecisionQueryService
from app.application.decision.streaming import DecisionStreamService
from app.application.history.ports import HistoryRepository
from app.application.places.service import PlaceService
from app.application.preferences.ports import PreferencesRepository
from app.core.config import Settings
from app.domain.places.ports import GeoPlaceProvider


class Container(Protocol):
    auth: AuthService
    settings: Settings
    decision_commands: DecisionCommandService
    decision_queries: DecisionQueryService
    decision_streams: DecisionStreamService
    location: GeoPlaceProvider
    places: PlaceService
    preferences: PreferencesRepository
    history: HistoryRepository
    choices: ChoiceRepository
