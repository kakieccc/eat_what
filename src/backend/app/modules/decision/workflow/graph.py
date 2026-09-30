from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.modules.decision.ports import FoodDecisionLlm
from app.modules.decision.workflow.context import Emitter, StateSaver, StepStarted
from app.modules.decision.workflow.events import NodeCompleted, NodeStarted
from app.modules.decision.workflow.nodes import (
    confirm_preferences,
    enrich_routes,
    filter_places,
    generate_explanations,
    parse_intent,
    rerank_places,
    score_places,
    search_places,
    select_diverse,
)
from app.modules.decision.workflow.state import State
from app.modules.places.ports import GeoPlaceProvider

Graph = CompiledStateGraph[State, Any, State, State]


def next_node(name: str, state: State) -> str:
    if name == "confirm_intent":
        return "confirm_intent" if state.get("awaiting_confirmation") else "search_places"
    if name in {"filter_places", "enrich_routes"} and not state.get("places"):
        return END
    transitions = {
        "parse_intent": "confirm_intent",
        "search_places": "filter_places",
        "filter_places": "enrich_routes",
        "enrich_routes": "score_places",
        "score_places": "rerank_places",
        "rerank_places": "select_diverse",
        "select_diverse": "generate_explanations",
        "generate_explanations": END,
    }
    return transitions[name]


def route(state: State) -> str:
    if state.get("awaiting_confirmation"):
        return END
    return state["next_node"]


def build_graph(
    amap: GeoPlaceProvider,
    llm: FoodDecisionLlm,
    emit: Emitter,
    step_started: StepStarted,
    save_state: StateSaver,
) -> Graph:
    builder = StateGraph(State)

    def wrapped(
        name: str, label: str, fn: Callable[[State], Awaitable[State]]
    ) -> Callable[[State], Awaitable[State]]:
        async def node(state: State) -> State:
            await step_started(state, name)
            task_id = state["task_id"]
            await emit(task_id, NodeStarted(node=name, label=label))
            started = time.monotonic()
            result = await fn(state)
            updated = cast(State, {**state, **result})
            updated["next_node"] = next_node(name, updated)
            await save_state(updated, name)
            await emit(
                task_id,
                NodeCompleted(
                    node=name,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    output_count=len(result["places"]) if "places" in result else None,
                ),
            )
            return {**result, "next_node": updated["next_node"]}

        return node

    definitions = [
        ("parse_intent", "正在理解你的偏好", parse_intent.build(llm)),
        ("confirm_intent", "正在确认条件", confirm_preferences.confirm),
        ("search_places", "正在搜索附近餐厅", search_places.build(amap)),
        ("filter_places", "正在筛选符合条件的地点", filter_places.filtering),
        ("enrich_routes", "正在查询高德步行路线", enrich_routes.build(amap)),
        ("score_places", "正在比较候选", score_places.scoring),
        ("rerank_places", "正在结合偏好排序", rerank_places.build(llm)),
        ("select_diverse", "正在挑选不同选择", select_diverse.select),
        ("generate_explanations", "正在生成推荐理由", generate_explanations.build(amap, llm)),
    ]
    for name, label, fn in definitions:
        builder.add_node(name, RunnableLambda(wrapped(name, label, fn)))
        builder.add_conditional_edges(name, route)
    builder.add_conditional_edges(START, route)
    return cast(Graph, builder.compile())
