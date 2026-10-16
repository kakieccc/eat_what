from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator


class Raw(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawResponse(Raw):
    status: Literal["1"]
    infocode: str = "10000"


class RawPhoto(Raw):
    url: str = ""


class RawBiz(Raw):
    rating: str | float | list[JsonValue] = ""
    cost: str | float | list[JsonValue] = ""
    opentime: str | list[JsonValue] = ""
    opentime2: str | list[JsonValue] = ""


class RawPlace(Raw):
    id: str
    name: str
    location: str
    type: str = ""
    typecode: str = ""
    tag: str | list[JsonValue] = ""
    atag: str | list[JsonValue] = ""
    address: str | list[JsonValue] = ""
    tel: str | list[JsonValue] = ""
    biz_ext: RawBiz = Field(default_factory=RawBiz)
    photos: list[RawPhoto] = Field(default_factory=list)

    @field_validator("biz_ext", mode="before")
    @classmethod
    def empty_biz(cls, value: object) -> object:
        return {} if value in ([], None, "") else value


class PlaceResponse(RawResponse):
    pois: list[RawPlace]


class RawRegeocode(Raw):
    formatted_address: str


class ReverseResponse(RawResponse):
    regeocode: RawRegeocode


class RawTip(Raw):
    location: str | list[JsonValue] = ""
    district: str | list[JsonValue] = ""
    name: str | list[JsonValue] = ""


class TipsResponse(RawResponse):
    tips: list[RawTip]


class FetchedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, JsonValue]
    fetched_at: AwareDatetime
