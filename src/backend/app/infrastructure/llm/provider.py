import json
from typing import TypeVar
from urllib.parse import urlsplit

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import APIError
from pydantic import Field, ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.base import Model
from app.domain.decision.models import Intent
from app.domain.places.models import Place
from app.domain.preferences.models import CUISINES, Preferences
from app.workflows.food_decision.prompts.explain import PROMPT as EXPLAIN
from app.workflows.food_decision.prompts.parse import PROMPT as PARSE
from app.workflows.food_decision.prompts.rerank import PROMPT as RERANK

T = TypeVar("T", bound=Model)
PROMPT_VERSION = "1"


class Ranking(Model):
    place_ids: list[str] = Field(min_length=1, max_length=10)


class Explanation(Model):
    place_id: str
    fragments: list[str] = Field(min_length=1, max_length=3)


class Explanations(Model):
    places: list[Explanation] = Field(min_length=1, max_length=3)


def evidence(place: Place) -> list[str]:
    values = [f"属于{'、'.join(place.cuisine_types)}", f"综合匹配分 {place.score:.0f}/100"]
    if place.route:
        values.append(f"步行约 {max(1, round(place.route.duration_seconds / 60))} 分钟")
    if place.average_cost is not None:
        values.append(f"参考人均 ¥{place.average_cost}")
    if place.rating is not None:
        values.append(f"高德评分 {place.rating:g}/5")
    if place.business_status == "open":
        values.append("高德数据显示营业中")
    return values


def validate_explanations(result: Explanations, places: list[Place]) -> dict[str, str]:
    expected = {p.id: set(evidence(p)) for p in places}
    if len(result.places) != len(expected) or {p.place_id for p in result.places} != set(expected):
        raise AppError("LLM_INVALID_OUTPUT", "推荐理由包含无效地点", 502)
    output = {}
    for item in result.places:
        if not set(item.fragments) <= expected[item.place_id] or len(set(item.fragments)) != len(
            item.fragments
        ):
            raise AppError("LLM_INVALID_OUTPUT", "推荐理由未通过事实校验", 502)
        output[item.place_id] = "；".join(item.fragments)
    return output


class OpenAICompatibleFoodDecisionLlm:
    def __init__(self, settings: Settings):
        # DeepSeek's default thinking mode rejects the forced tool choice used below.
        self.model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}}
            if urlsplit(settings.llm_base_url).hostname == "api.deepseek.com"
            else None,
        )

    async def structured(self, schema: type[T], prompt: str, data: object) -> T:
        try:
            template = ChatPromptTemplate.from_messages([("system", prompt), ("human", "{data}")])
            chain = template | self.model.with_structured_output(schema, method="function_calling")
            result = await chain.ainvoke({"data": json.dumps(data, ensure_ascii=False)})
            return schema.model_validate(result)
        except (ValidationError, ValueError, OutputParserException):
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except (APIError, TimeoutError):
            raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True) from None

    async def parse_intent(self, text: str) -> Intent:
        intent = await self.structured(Intent, PARSE, {"text": text, "allowedCuisines": CUISINES})
        if any(c not in CUISINES for c in intent.preferred_cuisines + intent.excluded_cuisines):
            raise AppError("LLM_INVALID_OUTPUT", "模型返回不支持的菜系", 502)
        return intent

    async def rerank(self, places: list[Place], preferences: Preferences) -> list[Place]:
        result = await self.structured(
            Ranking,
            RERANK,
            {
                "preferences": preferences.model_dump(
                    mode="json", exclude={"request_text", "origin"}
                ),
                "places": [{"id": p.id, "name": p.name, "evidence": evidence(p)} for p in places],
            },
        )
        if len(result.place_ids) != len(places) or set(result.place_ids) != {p.id for p in places}:
            raise AppError("LLM_INVALID_OUTPUT", "模型返回了无效候选顺序", 502)
        by_id = {p.id: p for p in places}
        return [by_id[key] for key in result.place_ids]

    async def explain(self, places: list[Place]) -> list[Place]:
        result = await self.structured(
            Explanations, EXPLAIN, [{"id": p.id, "evidence": evidence(p)} for p in places]
        )
        reasons = validate_explanations(result, places)
        return [p.model_copy(update={"reason": reasons[p.id]}) for p in places]
