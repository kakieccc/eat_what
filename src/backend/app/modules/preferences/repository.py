from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.preferences.mappers import preferences_from_row
from app.modules.preferences.models import Preference
from app.modules.preferences.schemas import Preferences


class PreferencesRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get(self, user_id: str) -> Preferences:
        async with self.sessions() as session:
            row = await session.scalar(select(Preference).where(Preference.user_id == user_id))
            return preferences_from_row(row)

    async def save(self, user_id: str, preferences: Preferences) -> Preferences:
        values = {
            "allowed_foods": preferences.allowed_foods,
            "preferred_foods": preferences.preferred_foods,
            "excluded_foods": preferences.excluded_foods,
            "typical_budget_per_person_min": preferences.budget_per_person.min,
            "typical_budget_per_person_max": preferences.budget_per_person.max,
            "typical_radius_meters": preferences.radius_meters,
            "preferred_tags": preferences.soft_preferences,
        }
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(Preference).where(Preference.user_id == user_id).with_for_update()
            )
            if row is None:
                session.add(Preference(user_id=user_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        return preferences
