import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlparse
from uuid import NAMESPACE_URL, uuid5

from app.infrastructure.amap.schemas import (
    PlaceResponse,
    RawPlace,
    ReverseResponse,
    TipsResponse,
)
from app.modules.location.geometry import distance
from app.modules.location.schemas import Origin, Point
from app.modules.places.schemas import Place

log = logging.getLogger("food.amap")


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
    photos = []
    for photo in raw.photos:
        try:
            url = urlparse(photo.url)
        except ValueError:
            continue
        if url.scheme == "https" and url.hostname:
            photos.append(photo.url)
            if len(photos) == 3:
                break
    return Place(
        id=str(uuid5(NAMESPACE_URL, "amap:" + raw.id)),
        external_id=raw.id,
        name=raw.name[:150],
        category_code=raw.typecode,
        category_name=raw.type[:200],
        cuisine_types=list(
            dict.fromkeys(
                v.strip()
                for v in [
                    raw.type.split(";")[-1],
                    *(raw.atag.split("/") if isinstance(raw.atag, str) else []),
                ]
                if v.strip() and v != "餐饮服务"
            )
        ),
        tags=[
            v.strip()
            for value in (raw.tag, raw.atag)
            if isinstance(value, str)
            for v in re.split("[,;，/]", value)
            if v.strip()
        ],
        address=raw.address[:250] if isinstance(raw.address, str) else "",
        location=location,
        straight_line_distance_meters=distance(origin, location),
        rating=float(rating) if rating is not None and rating <= 5 else None,
        average_cost=cost,
        opening_hours_text=hours[:200] if isinstance(hours, str) and hours else None,
        phone=raw.tel
        if isinstance(raw.tel, str) and re.fullmatch(r"[0-9+; -]{3,80}", raw.tel)
        else None,
        photos=photos,
        data_updated_at=fetched_at,
    )


def places(response: PlaceResponse, origin: Point, fetched_at: datetime) -> list[Place]:
    result = []
    skipped = 0
    for raw in response.pois:
        try:
            result.append(place(RawPlace.model_validate(raw), origin, fetched_at))
        except (ValueError, TypeError):
            skipped += 1
    if skipped:
        log.warning(json.dumps({"event": "amapPlacesSkipped", "count": skipped}))
    return result


def reverse(response: ReverseResponse, origin: Point) -> Origin:
    return Origin(
        longitude=origin.longitude,
        latitude=origin.latitude,
        address=response.regeocode.formatted_address[:200],
    )


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


def navigation(place: Place) -> str:
    return "https://uri.amap.com/marker?" + urlencode(
        {
            "position": coordinates(place.location),
            "name": place.name,
            "coordinate": "gaode",
            "src": "today-food",
            "callnative": "1",
        }
    )
