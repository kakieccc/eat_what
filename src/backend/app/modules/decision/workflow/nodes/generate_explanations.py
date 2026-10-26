from app.modules.decision.rules.explanations import explain
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


async def generate(state: State) -> State:
    return {"places": serialized([explain(p) for p in places(state)])}
