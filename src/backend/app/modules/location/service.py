from app.modules.location.schemas import Origin, Point
from app.modules.places.ports import GeoPlaceProvider


class LocationService:
    def __init__(self, provider: GeoPlaceProvider) -> None:
        self.provider = provider

    async def reverse(self, origin: Point) -> Origin:
        return await self.provider.reverse(origin)

    async def tips(self, query: str) -> list[Origin]:
        return await self.provider.tips(query)
