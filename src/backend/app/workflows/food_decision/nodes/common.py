from __future__ import annotations

from pydantic import JsonValue

from app.domain.places.models import Place
from app.workflows.food_decision.state import State


def places(state: State) -> list[Place]:
    return [Place.model_validate(item) for item in state.get("places", [])]


def serialized(items: list[Place]) -> list[dict[str, JsonValue]]:
    return [item.model_dump(mode="json") for item in items]
