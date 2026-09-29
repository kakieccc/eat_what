from typing import Protocol

from app.domain.preferences.models import Preferences


class PreferencesRepository(Protocol):
    async def get(self, user_id: str) -> Preferences: ...
    async def save(self, user_id: str, preferences: Preferences) -> Preferences: ...
