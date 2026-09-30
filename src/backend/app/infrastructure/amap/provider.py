import asyncio
import hashlib
import json
import logging
import random
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast
from urllib.parse import urlencode, urlparse
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.config import Settings
from app.core.errors import AppError
from app.modules.location.geometry import distance
from app.modules.location.schemas import Origin, Point
from app.modules.places.models import PlaceCache, RouteCache
from app.modules.places.schemas import Place, Route

log = logging.getLogger("food.amap")


class Raw(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawPhoto(Raw):
    url: str = ""


class RawBiz(Raw):
    rating: str | float | list[JsonValue] = ""
    cost: str | float | list[JsonValue] = ""
    opentime: str | list[JsonValue] = ""
    opentime2: str | list[JsonValue] = ""


class RawPlace(Raw):
    id: str
    name: str
    location: str
    type: str = ""
    typecode: str = ""
    address: str | list[JsonValue] = ""
    tel: str | list[JsonValue] = ""
    biz_ext: RawBiz = Field(default_factory=RawBiz)
    photos: list[RawPhoto] = Field(default_factory=list)

    @field_validator("biz_ext", mode="before")
    @classmethod
    def empty_biz(cls, value: object) -> object:
        return {} if value in ([], None, "") else value


class PlaceResponse(Raw):
    pois: list[RawPlace]
    fetched_at: datetime = Field(alias="_fetched_at")


class RawStep(Raw):
    polyline: str


class RawPath(Raw):
    distance: int = Field(ge=0)
    duration: int = Field(ge=0)
    steps: list[RawStep]


class RawRoute(Raw):
    paths: list[RawPath]


class RouteResponse(Raw):
    route: RawRoute


def number(value: object) -> Decimal | None:
    try:
        n = Decimal(str(value))
        return n if n.is_finite() and n >= 0 else None
    except InvalidOperation:
        return None


def point(value: str) -> Point:
    lon, lat = value.split(",")
    return Point(longitude=float(lon), latitude=float(lat))


def category(raw: RawPlace) -> str:
    text = raw.type + raw.name
    for word, cuisine in [
        ("火锅", "火锅"),
        ("烧烤", "烧烤"),
        ("面", "面馆"),
        ("轻食", "轻食"),
        ("沙拉", "轻食"),
        ("日本", "日韩料理"),
        ("韩国", "日韩料理"),
        ("泰国", "东南亚料理"),
        ("越南", "东南亚料理"),
        ("西餐", "西餐"),
        ("咖啡", "咖啡甜品"),
        ("甜品", "咖啡甜品"),
        ("快餐", "快餐"),
        ("小吃", "小吃"),
        ("中餐", "中餐"),
    ]:
        if word in text:
            return cuisine
    return "其他餐饮"


def normalize(raw: RawPlace, origin: Point) -> Place:
    location = point(raw.location)
    rating = number(raw.biz_ext.rating)
    cost = number(raw.biz_ext.cost)
    hours = raw.biz_ext.opentime2 or raw.biz_ext.opentime
    return Place(
        id=str(uuid5(NAMESPACE_URL, "amap:" + raw.id)),
        external_id=raw.id,
        name=raw.name[:150],
        category_code=raw.typecode,
        category_name=raw.type[:200],
        cuisine_types=[category(raw)],
        address=raw.address[:250] if isinstance(raw.address, str) else "",
        location=location,
        straight_line_distance_meters=distance(origin, location),
        rating=float(rating) if rating is not None and rating <= 5 else None,
        average_cost=cost,
        opening_hours_text=hours[:200] if isinstance(hours, str) and hours else None,
        phone=raw.tel
        if isinstance(raw.tel, str) and re.fullmatch(r"[0-9+; -]{3,80}", raw.tel)
        else None,
        photos=[p.url for p in raw.photos if urlparse(p.url).scheme == "https"][:3],
        data_updated_at=now(),
    )


def navigation(origin: Origin, place: Place) -> str:
    return "https://uri.amap.com/navigation?" + urlencode(
        {
            "from": f"{origin.amap()},{origin.address}",
            "to": f"{place.location.amap()},{place.name}",
            "mode": "walk",
            "coordinate": "gaode",
            "src": "today-food",
            "callnative": "1",
        }
    )


class AmapGeoPlaceProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
    ):
        self.client, self.sessions, self.settings = client, sessions, settings
        self.semaphore = asyncio.Semaphore(settings.amap_route_concurrency)
        self.route_request_lock = asyncio.Lock()
        self.next_route_request_at = 0.0

    async def wait_for_route_slot(self) -> None:
        async with self.route_request_lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0.0, self.next_route_request_at - loop.time()))
            self.next_route_request_at = loop.time() + 0.5

    @staticmethod
    def navigation(origin: Origin, place: Place) -> str:
        return navigation(origin, place)

    async def request(
        self, operation: str, params: dict[str, str], route: bool = False
    ) -> dict[str, JsonValue]:
        allowed = {
            "/v3/place/around",
            "/v3/place/detail",
            "/v3/geocode/regeo",
            "/v3/assistant/inputtips",
            "/v3/direction/walking",
        }
        if operation not in allowed:
            raise AppError("AMAP_INVALID_OPERATION", "地图操作不受支持")
        cache_key = hashlib.sha256(
            json.dumps([operation, params, "v2"], sort_keys=True).encode()
        ).hexdigest()
        table = RouteCache if route else PlaceCache
        async with self.sessions() as session:
            cached = await session.scalar(
                select(table).where(table.cache_key == cache_key, table.expires_at > now())
            )
            if cached:
                log.info("provider", extra={"operation": operation, "cacheHit": True})
                return cast(dict[str, JsonValue], cast(PlaceCache | RouteCache, cached).payload)
        for attempt in range(3):
            try:
                if route:
                    await self.wait_for_route_slot()
                response = await self.client.get(
                    "https://restapi.amap.com" + operation,
                    params={**params, "key": self.settings.amap_web_service_key.get_secret_value()},
                    timeout=self.settings.amap_timeout_seconds,
                )
                response.raise_for_status()
                payload: dict[str, JsonValue] = response.json()
                payload["_fetched_at"] = now().isoformat()
                if payload.get("status") != "1":
                    code = str(payload.get("infocode"))
                    retryable = code in {
                        "10004", "10014", "10015", "10016", "10017",
                        "10019", "10020", "10021", "10022", "10023", "10029",
                    }
                    raise AppError(
                        "AMAP_RATE_LIMITED" if retryable else "AMAP_UNAVAILABLE",
                        "高德服务请求失败，请检查 Key 权限与配额",
                        502,
                        retryable,
                    )
                ttl = (
                    self.settings.amap_route_cache_ttl_seconds
                    if route
                    else self.settings.amap_cache_ttl_seconds
                )
                async with self.sessions.begin() as session:
                    await session.execute(
                        insert(table)
                        .values(
                            cache_key=cache_key,
                            payload=payload,
                            expires_at=now() + timedelta(seconds=ttl),
                        )
                        .on_conflict_do_update(
                            index_elements=["cache_key"],
                            set_={"payload": payload, "expires_at": now() + timedelta(seconds=ttl)},
                        )
                    )
                return payload
            except (httpx.HTTPError, AppError) as error:
                retryable = not isinstance(error, AppError) or error.retryable
                if isinstance(error, httpx.HTTPStatusError):
                    retryable = (
                        error.response.status_code == 429 or error.response.status_code >= 500
                    )
                if attempt == 2 or not retryable:
                    raise AppError(
                        "ROUTE_UNAVAILABLE" if route else "AMAP_UNAVAILABLE",
                        "步行路线服务不可用" if route else "地图服务暂时不可用",
                        502,
                        retryable,
                    ) from None
                await asyncio.sleep(0.2 * 2**attempt + random.uniform(0, 0.1))
            except (ValueError, TypeError):
                raise AppError("AMAP_SCHEMA_ERROR", "地图响应格式异常", 502) from None
        raise AssertionError("unreachable")

    async def search(
        self, origin: Point, radius: int, limit: int = 30, keywords: str = ""
    ) -> list[Place]:
        places: list[Place] = []
        try:
            for page in range(1, 3):
                data = await self.request(
                    "/v3/place/around",
                    {
                        "location": origin.amap(),
                        "radius": str(radius),
                        "types": "050000",
                        "extensions": "all",
                        "offset": "25",
                        "page": str(page),
                        "sortrule": "distance",
                        "keywords": keywords,
                    },
                )
                parsed = PlaceResponse.model_validate(data)
                batch = parsed.pois
                places.extend(
                    normalize(p, origin).model_copy(update={"data_updated_at": parsed.fetched_at})
                    for p in batch
                )
                if len(places) >= limit or len(batch) < 25:
                    break
            return list({p.id: p for p in places}.values())[:limit]
        except (ValidationError, ValueError):
            raise AppError("AMAP_SCHEMA_ERROR", "餐厅数据格式异常", 502) from None

    async def detail(self, external_id: str, origin: Point) -> Place:
        data = await self.request("/v3/place/detail", {"id": external_id, "extensions": "all"})
        try:
            parsed = PlaceResponse.model_validate(data)
            rows = parsed.pois
            if not rows:
                raise AppError("PLACE_NOT_FOUND", "地点详情暂不可用", 404)
            return normalize(rows[0], origin).model_copy(
                update={"data_updated_at": parsed.fetched_at}
            )
        except (ValidationError, ValueError):
            raise AppError("AMAP_SCHEMA_ERROR", "地点详情格式异常", 502) from None

    async def walking(self, origin: Point, destination: Point) -> Route | None:
        async with self.semaphore:
            data = await self.request(
                "/v3/direction/walking",
                {"origin": origin.amap(), "destination": destination.amap()},
                route=True,
            )
        try:
            paths = RouteResponse.model_validate(data).route.paths
            if not paths:
                return None
            best = min(paths, key=lambda p: p.duration)
            polyline = [
                point(pair) for step in best.steps for pair in step.polyline.split(";") if pair
            ]
            if not polyline:
                raise ValueError("Missing geometry")
            stride = max(1, math_ceil(len(polyline) / 1999))
            return Route(
                distance_meters=best.distance,
                duration_seconds=best.duration,
                polyline=polyline[::stride]
                + ([polyline[-1]] if polyline[-1] != polyline[::stride][-1] else []),
            )
        except (ValueError, ValidationError):
            raise AppError("AMAP_SCHEMA_ERROR", "步行路线数据格式异常", 502) from None

    async def reverse(self, origin: Point) -> Origin:
        data = await self.request(
            "/v3/geocode/regeo", {"location": origin.amap(), "extensions": "base"}
        )
        regeo = data.get("regeocode")
        if not isinstance(regeo, dict) or not isinstance(regeo.get("formatted_address"), str):
            raise AppError("AMAP_SCHEMA_ERROR", "地址解析失败", 502)
        return Origin(**origin.model_dump(), address=regeo["formatted_address"])

    async def tips(self, keywords: str) -> list[Origin]:
        data = await self.request(
            "/v3/assistant/inputtips", {"keywords": keywords, "datatype": "poi"}
        )
        tips = data.get("tips")
        if not isinstance(tips, list):
            raise AppError("AMAP_SCHEMA_ERROR", "地址搜索响应异常", 502)
        result = []
        for tip in tips:
            if isinstance(tip, dict) and isinstance(tip.get("location"), str) and tip["location"]:
                try:
                    p = point(str(tip["location"]))
                    result.append(
                        Origin(
                            **p.model_dump(),
                            address=(str(tip.get("district", "")) + str(tip.get("name", "")))[:200],
                        )
                    )
                except ValueError:
                    continue
        return result[:10]


def math_ceil(value: float) -> int:
    import math

    return math.ceil(value)
