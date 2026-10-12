import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from uuid import NAMESPACE_URL, uuid5

from app.infrastructure.amap.schemas import (
    PlaceResponse,
    RawPlace,
    ReverseResponse,
    RouteResponse,
    TipsResponse,
)
from app.modules.location.geometry import distance
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place, Route


def coordinates(value: Point) -> str:
    return f"{value.longitude:.6f},{value.latitude:.6f}"


def point(value: str) -> Point:
    lon, lat = value.split(",")
    return Point(longitude=float(lon), latitude=float(lat))


def number(value: object) -> Decimal | None:
    try:
        n = Decimal(str(value))
        return n if n.is_finite() and n >= 0 else None
    except InvalidOperation:
        return None


def place(raw: RawPlace, origin: Point, fetched_at: datetime) -> Place:
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
        cuisine_types=[],
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
        data_updated_at=fetched_at,
    )


def places(response: PlaceResponse, origin: Point, fetched_at: datetime) -> list[Place]:
    return [place(raw, origin, fetched_at) for raw in response.pois]


def walking(response: RouteResponse) -> Route | None:
    paths = response.route.paths
    if not paths:
        return None
    best = min(paths, key=lambda p: p.duration)
    polyline = [point(pair) for step in best.steps for pair in step.polyline.split(";") if pair]
    if not polyline:
        raise ValueError("Missing geometry")
    stride = max(1, math.ceil(len(polyline) / 1999))
    sampled = polyline[::stride]
    if sampled[-1] != polyline[-1]:
        sampled.append(polyline[-1])
    return Route(
        distance_meters=best.distance,
        duration_seconds=best.duration,
        polyline=sampled,
    )


def reverse(response: ReverseResponse, origin: Point) -> Origin:
    return Origin(**origin.model_dump(), address=response.regeocode.formatted_address)


def tips(response: TipsResponse) -> list[Origin]:
    result = []
    for tip in response.tips:
        if not isinstance(tip.location, str) or not tip.location:
            continue
        try:
            location = point(tip.location)
        except ValueError:
            continue
        district = tip.district if isinstance(tip.district, str) else ""
        name = tip.name if isinstance(tip.name, str) else ""
        result.append(Origin(**location.model_dump(), address=(district + name)[:200]))
    return result[:10]


def navigation(origin: Origin, place: Place) -> str:
    return "https://uri.amap.com/navigation?" + urlencode(
        {
            "from": f"{coordinates(origin)},{origin.address}",
            "to": f"{coordinates(place.location)},{place.name}",
            "mode": "walk",
            "coordinate": "gaode",
            "src": "today-food",
            "callnative": "1",
        }
    )
