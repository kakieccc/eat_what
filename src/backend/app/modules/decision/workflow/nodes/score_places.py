
from app.modules.decision.rules.policies import score_places
from app.modules.decision.schemas import DecisionRequest
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


async def scoring(state: State) -> State:
    request = DecisionRequest.model_validate(state["request"])
    return {
        "places": serialized(
            score_places(
                places(state),
                request,
                state.get("action", ""),
                state.get("recent", []),
                state.get("old_cuisines", []),
            )
        )
    }
