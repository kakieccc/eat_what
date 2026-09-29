from __future__ import annotations

from app.domain.geo.models import Origin, Point
from app.domain.places.ports import GeoPlaceProvider


class LocationService:
    def __init__(self, provider: GeoPlaceProvider) -> None:
        self.provider = provider

    async def reverse(self, point: Point) -> Origin:
        return await self.provider.reverse(point)

    async def tips(self, keywords: str) -> list[Origin]:
        return await self.provider.tips(keywords)
