from app.modules.decision.rules.explanations import explain
from app.modules.decision.workflow.state import State


async def generate(state: State) -> State:
    return {"places": [explain(p) for p in state["places"]]}
