from typing import Protocol

from app.domain.places.models import Place


class PlaceRepository(Protocol):
    async def read(self, user_id: str, place_key: str) -> Place: ...
