from pydantic import Field

from app.core.models import Model


class PlaceChoiceRequest(Model):
    candidate_id: str = Field(min_length=1, max_length=100)
    feedback: str = Field(default="", max_length=300)
