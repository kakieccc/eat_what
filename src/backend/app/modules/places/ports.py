from __future__ import annotations

from typing import Protocol

from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place, Route


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
    ) -> list[Place]: ...
    async def detail(
        self, external_id: str, origin: Point, *, deadline: float | None = None
    ) -> Place: ...
    async def walking(
        self, origin: Point, destination: Point, *, deadline: float | None = None
    ) -> Route | None: ...
    def navigation(self, origin: Origin, place: Place) -> str: ...
