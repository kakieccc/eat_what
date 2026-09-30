from typing import Protocol

from app.modules.preferences.schemas import Preferences


class PreferencesRepository(Protocol):
    async def get(self, user_id: str) -> Preferences: ...
    async def save(self, user_id: str, preferences: Preferences) -> Preferences: ...
