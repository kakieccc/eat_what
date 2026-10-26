from dataclasses import dataclass
from typing import Protocol

from app.modules.preferences.schemas import (
    LearnedPreferences,
    PreferencesResponse,
    PreferencesUpdate,
)
from app.modules.task.types import TaskClaim


class PreferencesRepository(Protocol):
    async def get(self, user_id: str) -> PreferencesResponse: ...
    async def save(self, user_id: str, update: PreferencesUpdate) -> PreferencesResponse: ...


@dataclass(frozen=True)
class MealEvidence:
    id: str
    meal_number: int
    active_changes: dict[str, object]
    request_text: str
    restaurant_facts: dict[str, object]


class MemoryRepository(Protocol):
    async def renew(self, claim: TaskClaim, lease_seconds: int) -> None: ...
    async def samples(self, claim: TaskClaim) -> list[MealEvidence]: ...
    async def finish(self, claim: TaskClaim, result: LearnedPreferences | None) -> None: ...
