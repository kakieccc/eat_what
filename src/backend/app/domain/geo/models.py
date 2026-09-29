from pydantic import Field

from app.domain.base import Model


class Point(Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    def amap(self) -> str:
        return f"{self.longitude:.6f},{self.latitude:.6f}"


class Origin(Point):
    address: str = Field(default="", max_length=200)
