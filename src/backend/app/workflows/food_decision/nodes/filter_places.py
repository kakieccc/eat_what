
from app.domain.decision.models import DecisionRequest
from app.domain.decision.policies import eligible, score_places
from app.workflows.food_decision.nodes.common import places, serialized
from app.workflows.food_decision.state import State


async def filtering(state: State) -> State:
    request = DecisionRequest.model_validate(state["request"])
    kept, summary = eligible(places(state), request, state.get("excluded", []))
    ordered = score_places(
        kept,
        request,
        state.get("action", ""),
        state.get("recent", []),
        state.get("old_cuisines", []),
    )
    return {"places": serialized(ordered[:15]), "filter_summary": summary}
