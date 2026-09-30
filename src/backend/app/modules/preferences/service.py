from app.modules.preferences.ports import PreferencesRepository
from app.modules.preferences.schemas import Preferences


class PreferencesService:
    def __init__(self, repository: PreferencesRepository) -> None:
        self.repository = repository

    async def get(self, user_id: str) -> Preferences:
        return await self.repository.get(user_id)

    async def save(self, user_id: str, preferences: Preferences) -> Preferences:
        return await self.repository.save(user_id, preferences)
