from typing import Protocol

from app.application.auth.service import AuthService
from app.application.choice.service import ChoiceService
from app.application.decision.commands import DecisionCommandService
from app.application.decision.queries import DecisionQueryService
from app.application.decision.streaming import DecisionStreamService
from app.application.history.service import HistoryService
from app.application.location.service import LocationService
from app.application.places.service import PlaceService
from app.application.preferences.service import PreferencesService
from app.core.config import Settings


class Container(Protocol):
    auth: AuthService
    settings: Settings
    decision_commands: DecisionCommandService
    decision_queries: DecisionQueryService
    decision_streams: DecisionStreamService
    location: LocationService
    places: PlaceService
    preferences: PreferencesService
    history: HistoryService
    choices: ChoiceService
