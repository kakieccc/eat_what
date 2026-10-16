from app.core.errors import AppError
from app.modules.decision.schemas import DecisionRequest, Explanations, Intent, Ranking
from app.modules.places.schemas import Place
from app.modules.preferences.rules import require_supported_radius


def evidence(place: Place) -> list[str]:
    values = [f"高德分类：{place.category_name}"] if place.category_name else []
    values.append(f"距出发位置直线 {place.straight_line_distance_meters} 米")
    if place.average_cost is not None:
        values.append(f"参考人均 ¥{place.average_cost}")
    if place.rating is not None:
        values.append(f"高德评分 {place.rating:g}/5")
    return values


def validate_intent(intent: Intent, request: DecisionRequest) -> None:
    before, after = request.preferences, intent.preferences
    require_supported_radius(after.radius_meters)
    if (
        intent.has_conflict
        or after.radius_meters > before.radius_meters
        or (
            before.budget_per_person.max is not None
            and (
                after.budget_per_person.max is None
                or after.budget_per_person.max > before.budget_per_person.max
            )
        )
        or (
            before.budget_per_person.min is not None
            and (
                after.budget_per_person.min is None
                or after.budget_per_person.min < before.budget_per_person.min
            )
        )
        or not set(before.excluded_foods) <= set(after.excluded_foods)
        or (before.allowed_foods and (
            not after.allowed_foods or not set(after.allowed_foods) <= set(before.allowed_foods)
        ))
    ):
        raise AppError("INPUT_CONFLICT", "表单与补充说明存在冲突", 422)
    if any(not word.strip() or len(word) > 30 for word in intent.search_keywords):
        raise AppError("LLM_INVALID_OUTPUT", "搜索关键词无效", 502)


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
