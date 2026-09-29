from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.domain.decision.models import DecisionRequest
from app.domain.decision.ports import FoodDecisionLlm
from app.domain.places.ports import GeoPlaceProvider
from app.workflows.food_decision.context import Emitter, Persist, StateSaver, StepStarted
from app.workflows.food_decision.events import NodeCompleted, NodeStarted
from app.workflows.food_decision.nodes import (
    confirm_preferences,
    enrich_routes,
    filter_places,
    generate_explanations,
    load_context,
    normalize_places,
    parse_intent,
    persist_empty_result,
    persist_result,
    rerank_places,
    score_places,
    search_places,
    select_diverse,
)
from app.workflows.food_decision.state import State

Graph = CompiledStateGraph[State, Any, State, State]


def build_graph(
    amap: GeoPlaceProvider,
    llm: FoodDecisionLlm,
    persist: Persist,
    emit: Emitter,
    step_started: StepStarted,
    save_state: StateSaver,
) -> Graph:
    builder = StateGraph(State)

    def wrapped(
        name: str,
        label: str,
        fn: Callable[[State], Awaitable[State]],
    ) -> Callable[[State], Awaitable[State]]:
        async def node(state: State) -> State:
            await step_started(state, name)
            task_id = state.get("task_id", state["decision_run_id"])
            await emit(task_id, NodeStarted(node=name, label=label))
            started = time.monotonic()
            result = await fn(state)
            next_state = cast(State, {**state, **result, "current_node": name})
            await save_state(next_state, name)
            await emit(
                task_id,
                NodeCompleted(
                    node=name,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    output_count=len(result["places"]) if "places" in result else None,
                ),
            )
            return result

        return node

    async def await_confirmation(_: State) -> State:
        return {}

    definitions = [
        ("load_context", "正在读取本次偏好", load_context.build()),
        ("parse_intent", "正在理解你的偏好", parse_intent.build(llm)),
        ("confirm_intent", "正在确认条件", confirm_preferences.build()),
        ("await_confirmation", "等待确认条件", await_confirmation),
        ("search_places", "正在搜索附近餐厅", search_places.build(amap)),
        ("normalize_places", "正在整理地点信息", normalize_places.build()),
        ("filter_places", "正在筛选符合条件的地点", filter_places.build()),
        ("enrich_routes", "正在查询高德步行路线", enrich_routes.build(amap)),
        ("score_places", "正在比较候选", score_places.build()),
        ("rerank_places", "正在结合偏好排序", rerank_places.build(llm)),
        ("select_diverse", "正在挑选不同选择", select_diverse.build()),
        (
            "generate_explanations",
            "正在生成推荐理由",
            generate_explanations.build(amap, llm),
        ),
        ("persist_result", "正在保存推荐", persist_result.build(persist)),
        ("persist_empty_result", "正在保存筛选结果", persist_empty_result.build(persist)),
    ]
    for name, label, fn in definitions:
        builder.add_node(name, RunnableLambda(wrapped(name, label, fn)))

    builder.add_edge(START, "load_context")

    def next_after_load(state: State) -> str:
        if state.get("resume_from"):
            return str(state["resume_from"])
        continuation = {
            "load_context": None,
            "parse_intent": "confirm_intent",
            "confirm_intent": (
                "await_confirmation" if state.get("awaiting_confirmation") else "search_places"
            ),
            "await_confirmation": "await_confirmation",
            "search_places": "normalize_places",
            "normalize_places": "filter_places",
            "filter_places": "enrich_routes" if state.get("places") else "persist_empty_result",
            "enrich_routes": "score_places" if state.get("places") else "persist_empty_result",
            "score_places": "rerank_places",
            "rerank_places": "select_diverse",
            "select_diverse": "generate_explanations",
            "generate_explanations": "persist_result",
        }
        if state.get("current_node") in continuation:
            next_node = continuation[state["current_node"]]
            if next_node:
                return next_node
        return (
            "parse_intent"
            if DecisionRequest.model_validate(state["request"]).request_text
            else "search_places"
        )

    builder.add_conditional_edges("load_context", next_after_load)
    builder.add_edge("parse_intent", "confirm_intent")
    builder.add_conditional_edges(
        "confirm_intent",
        lambda state: (
            "await_confirmation" if state.get("awaiting_confirmation") else "search_places"
        ),
    )
    builder.add_edge("await_confirmation", END)
    builder.add_edge("search_places", "normalize_places")
    builder.add_edge("normalize_places", "filter_places")
    builder.add_conditional_edges(
        "filter_places",
        lambda state: "enrich_routes" if state.get("places") else "persist_empty_result",
    )
    builder.add_conditional_edges(
        "enrich_routes",
        lambda state: "score_places" if state.get("places") else "persist_empty_result",
    )
    for first, second in [
        ("score_places", "rerank_places"),
        ("rerank_places", "select_diverse"),
        ("select_diverse", "generate_explanations"),
        ("generate_explanations", "persist_result"),
        ("persist_result", END),
        ("persist_empty_result", END),
    ]:
        builder.add_edge(first, second)
    return cast(Graph, builder.compile())
