from __future__ import annotations

from pydantic import JsonValue

from app.modules.decision.workflow.state import State
from app.modules.places.schemas import Place


def places(state: State) -> list[Place]:
    return [Place.model_validate(item) for item in state.get("places", [])]


def serialized(items: list[Place]) -> list[dict[str, JsonValue]]:
    return [item.model_dump(mode="json") for item in items]
