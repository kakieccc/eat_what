from typing import Protocol

from app.modules.location.schemas import Origin, Point


class LocationProvider(Protocol):
    async def reverse(self, origin: Point, *, deadline: float | None = None) -> Origin: ...
    async def tips(self, keywords: str, *, deadline: float | None = None) -> list[Origin]: ...
