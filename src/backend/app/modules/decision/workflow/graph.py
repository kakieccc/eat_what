from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.workflow.context import Emitter, StepCallback
from app.modules.decision.workflow.events import NodeCompleted, NodeStarted
from app.modules.decision.workflow.nodes import (
    filter_places,
    generate_explanations,
    rerank_places,
    search_places,
    select_diverse,
)
from app.modules.decision.workflow.state import State
from app.modules.places.service import PlaceService
from app.modules.task.types import TaskClaim

Graph = CompiledStateGraph[State, Any, State, State]


def build_graph(
    places: PlaceService,
    llm: FoodDecisionLlm,
    emit: Emitter,
    step_started: StepCallback,
    step_completed: StepCallback,
) -> Graph:
    builder = StateGraph(State)

    def wrapped(
        name: str, label: str, fn: Callable[[State], Awaitable[State]]
    ) -> Callable[[State], Awaitable[State]]:
        async def node(state: State) -> State:
            await step_started(state, name)
            claim = TaskClaim(task_id=state["task_id"], lease_token=state["lease_token"])
            await emit(claim, NodeStarted(node=name, label=label))
            started = time.monotonic()
            result = await fn(state)
            await step_completed(state, name)
            await emit(
                claim,
                NodeCompleted(
                    node=name,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    output_count=len(result["places"]) if "places" in result else None,
                ),
            )
            return result

        return node

    definitions = [
        ("search_places", "正在搜索附近餐厅", search_places.build(places)),
        ("filter_places", "正在筛选符合条件的地点", filter_places.build(places, llm)),
        ("rerank_places", "正在结合偏好排序", rerank_places.build(llm)),
        ("select_diverse", "正在挑选不同选择", select_diverse.select),
        ("generate_explanations", "正在整理推荐理由", generate_explanations.generate),
    ]
    for name, label, fn in definitions:
        builder.add_node(name, RunnableLambda(wrapped(name, label, fn)))
    builder.add_edge(START, "search_places")
    builder.add_edge("search_places", "filter_places")
    builder.add_conditional_edges(
        "filter_places", lambda state: "rerank_places" if state["places"] else END
    )
    builder.add_edge("rerank_places", "select_diverse")
    builder.add_edge("select_diverse", "generate_explanations")
    builder.add_edge("generate_explanations", END)
    return cast(Graph, builder.compile())
