from app.core.errors import AppError
from app.modules.decision.schemas import Ranking
from app.modules.places.schemas import Place


def evidence(place: Place) -> list[str]:
    values = [f"高德分类：{place.category_name}"] if place.category_name else []
    values.append(f"距出发位置直线 {place.straight_line_distance_meters} 米")
    if place.average_cost is not None:
        values.append(f"参考人均 ¥{place.average_cost}")
    if place.rating is not None:
        values.append(f"高德评分 {place.rating:g}/5")
    if place.opening_hours_text:
        values.append(f"高德营业时间：{place.opening_hours_text}")
    return values


def sources(place: Place) -> set[str]:
    return {
        place.name,
        place.category_name,
        *place.cuisine_types,
        *place.tags,
        *evidence(place),
    } - {""}


def validate_ranking(result: Ranking, places: list[Place]) -> None:
    expected = {p.id: sources(p) for p in places}
    if len(result.places) != len(places) or {p.place_id for p in result.places} != set(expected):
        raise AppError("LLM_INVALID_OUTPUT", "模型返回了无效候选评分", 502)
    for item in result.places:
        if not set(item.evidence) <= expected[item.place_id] or (
            item.score > 0 and not item.evidence
        ):
            raise AppError("LLM_INVALID_OUTPUT", "评分依据无效", 502)
