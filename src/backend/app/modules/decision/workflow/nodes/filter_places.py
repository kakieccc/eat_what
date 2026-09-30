
from app.modules.decision.rules.policies import eligible, score_places
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


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
