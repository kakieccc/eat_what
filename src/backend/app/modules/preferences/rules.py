from typing import get_args

from app.core.errors import AppError
from app.modules.preferences.schemas import ALLOWED_FOOD_LIMIT, SearchRadius


def require_supported_radius(radius_meters: int) -> None:
    if radius_meters not in get_args(SearchRadius):
        raise AppError("UNSUPPORTED_RADIUS", "请选择 500 米、1 km、2 km 或 5 km 的搜索半径", 422)


def require_allowed_food_limit(foods: list[str]) -> None:
    if len(foods) > ALLOWED_FOOD_LIMIT:
        raise AppError("INVALID_INPUT", f"限定食物类型最多 {ALLOWED_FOOD_LIMIT} 项，请调整条件后重新推荐", 422)
