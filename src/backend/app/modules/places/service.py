import asyncio

from app.core.concurrency import deadline_after, gather_cancel_on_error
from app.core.errors import AppError
from app.modules.location.schemas import Point
from app.modules.places.ports import GeoPlaceProvider, PlaceRepository
from app.modules.places.schemas import Place, PlaceSearchPage


class PlaceService:
    def __init__(
        self, repository: PlaceRepository, provider: GeoPlaceProvider, timeout_seconds: float
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    async def search(
        self,
        origin: Point,
        radius_meters: int,
        limit: int = 30,
        keywords: list[str] | None = None,
        *,
        deadline: float | None = None,
        page: int = 1,
    ) -> PlaceSearchPage:
        until = deadline_after(self.timeout_seconds, deadline)
        try:
            async with asyncio.timeout_at(until):
                batches = await gather_cancel_on_error(
                    *(
                        self.provider.search(
                            origin, radius_meters, limit, word, deadline=until, page=page
                        )
                        for word in keywords or [""]
                    )
                )
                unique: dict[str, Place] = {}
                for batch in batches:
                    for place in batch.places:
                        unique.setdefault(place.id, place)
                selected = sorted(
                    unique.values(), key=lambda p: (p.straight_line_distance_meters, p.id)
                )[:limit]
                if asyncio.get_running_loop().time() >= until:
                    raise TimeoutError
                return PlaceSearchPage(
                    places=selected, has_more=any(batch.has_more for batch in batches)
                )
        except TimeoutError:
            raise AppError("AMAP_UNAVAILABLE", "地图服务暂时不可用", 502, True) from None

    async def read(self, user_id: str, place_key: str) -> Place:
        return self.with_navigation(await self.repository.read(user_id, place_key))

    def with_navigation(self, place: Place) -> Place:
        return place.model_copy(update={"navigation_url": self.provider.navigation(place)})
