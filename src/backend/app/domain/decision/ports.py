from typing import Protocol

from app.domain.decision.models import Intent
from app.domain.places.models import Place
from app.domain.preferences.models import Preferences


class FoodDecisionLlm(Protocol):
    async def parse_intent(self, text: str) -> Intent: ...
    async def rerank(self, places: list[Place], preferences: Preferences) -> list[Place]: ...
    async def explain(self, places: list[Place]) -> list[Place]: ...
