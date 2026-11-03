
from app.modules.decision.rules.policies import diverse
from app.modules.decision.workflow.state import State


async def select(state: State) -> State:
    return {"places": diverse(state["places"])}
