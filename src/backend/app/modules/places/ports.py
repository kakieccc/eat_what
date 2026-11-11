from __future__ import annotations

from typing import Protocol

from app.modules.location.schemas import Point
from app.modules.places.schemas import Place, PlaceSearchPage


class PlaceRepository(Protocol):
    async def read(self, user_id: str, place_key: str) -> Place: ...


class GeoPlaceProvider(Protocol):
    async def search(
        self,
        origin: Point,
        radius: int,
        limit: int = 30,
        keywords: str = "",
        *,
        deadline: float | None = None,
        page: int = 1,
    ) -> PlaceSearchPage: ...
    def navigation(self, place: Place) -> str: ...
