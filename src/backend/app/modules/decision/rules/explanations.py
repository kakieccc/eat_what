from app.modules.decision.rules.llm import evidence
from app.modules.places.schemas import Place


def explain(place: Place) -> Place:
    parts = [place.reason, *(fact for fact in evidence(place) if fact not in place.reason)]
    if place.average_cost is None:
        parts.append("人均暂无数据")
    if place.rating is None:
        parts.append("评分暂无数据")
    return place.model_copy(update={"reason": "；".join(dict.fromkeys(part for part in parts if part))})
