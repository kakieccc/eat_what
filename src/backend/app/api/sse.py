from collections.abc import AsyncIterator

from app.workflows.food_decision.events import DecisionEvent


def frame(event: DecisionEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json(by_alias=True)}\n\n"


async def encode(events: AsyncIterator[DecisionEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield frame(event)
