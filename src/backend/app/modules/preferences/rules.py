from app.core.errors import AppError
from app.modules.preferences.schemas import SEARCH_RADII


def require_supported_radius(radius_meters: int) -> None:
    if radius_meters not in SEARCH_RADII:
        raise AppError(
            "UNSUPPORTED_RADIUS", "搜索范围仅支持 500 米、1 km、2 km、5 km，请重新选择", 422
        )
