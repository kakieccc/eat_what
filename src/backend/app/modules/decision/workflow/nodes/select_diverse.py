
from app.modules.decision.rules.policies import diverse
from app.modules.decision.workflow.nodes.common import places, serialized
from app.modules.decision.workflow.state import State


async def select(state: State) -> State:
    return {"places": serialized(diverse(places(state)))}
