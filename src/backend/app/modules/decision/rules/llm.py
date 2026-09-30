from app.core.errors import AppError
from app.modules.decision.schemas import Explanations, Intent, Ranking
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import CUISINES


def evidence(place: Place) -> list[str]:
    values = [f"属于{'、'.join(place.cuisine_types)}", f"综合匹配分 {place.score:.0f}/100"]
    if place.route:
        values.append(f"步行约 {max(1, round(place.route.duration_seconds / 60))} 分钟")
    if place.average_cost is not None:
        values.append(f"参考人均 ¥{place.average_cost}")
    if place.rating is not None:
        values.append(f"高德评分 {place.rating:g}/5")
    if place.business_status == "open":
        values.append("高德数据显示营业中")
    return values


def validate_intent(intent: Intent) -> None:
    if any(c not in CUISINES for c in intent.preferred_cuisines + intent.excluded_cuisines):
        raise AppError("LLM_INVALID_OUTPUT", "模型返回不支持的菜系", 502)


def validate_ranking(result: Ranking, places: list[Place]) -> None:
    if len(result.place_ids) != len(places) or set(result.place_ids) != {p.id for p in places}:
        raise AppError("LLM_INVALID_OUTPUT", "模型返回了无效候选顺序", 502)


def validate_explanations(result: Explanations, places: list[Place]) -> dict[str, str]:
    expected = {p.id: set(evidence(p)) for p in places}
    if len(result.places) != len(expected) or {p.place_id for p in result.places} != set(expected):
        raise AppError("LLM_INVALID_OUTPUT", "推荐理由包含无效地点", 502)
    output = {}
    for item in result.places:
        if not set(item.fragments) <= expected[item.place_id] or len(set(item.fragments)) != len(
            item.fragments
        ):
            raise AppError("LLM_INVALID_OUTPUT", "推荐理由未通过事实校验", 502)
        output[item.place_id] = "；".join(item.fragments)
    return output
