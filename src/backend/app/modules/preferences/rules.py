from typing import get_args

from app.core.errors import AppError
from app.modules.preferences.schemas import SearchRadius


def require_supported_radius(radius_meters: int) -> None:
    if radius_meters not in get_args(SearchRadius):
        raise AppError("UNSUPPORTED_RADIUS", "请选择 500 米、1 km、2 km 或 5 km 的搜索半径", 422)
