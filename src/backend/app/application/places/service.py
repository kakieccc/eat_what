from app.application.places.ports import PlaceRepository
from app.domain.geo.models import Origin
from app.domain.places.models import Place
from app.domain.places.ports import GeoPlaceProvider


class PlaceService:
    def __init__(self, repository: PlaceRepository, provider: GeoPlaceProvider) -> None:
        self.repository = repository
        self.provider = provider

    async def search(
        self, origin: Origin, radius_meters: int, limit: int, keywords: list[str]
    ) -> list[Place]:
        return await self.provider.search(origin, radius_meters, limit, "|".join(keywords))

    async def read(self, user_id: str, place_key: str) -> Place:
        return await self.repository.read(user_id, place_key)
