from app.core.errors import AppError
from app.modules.decision.ports import StructuredLlm
from app.modules.decision.rules.llm import (
    sources,
    validate_ranking,
)
from app.modules.decision.rules.policies import sort_places
from app.modules.decision.schemas import DecisionRequest, FoodAssessments, Ranking
from app.modules.decision.workflow.prompts.filter import PROMPT as FILTER
from app.modules.decision.workflow.prompts.rerank import PROMPT as RERANK
from app.modules.places.schemas import Place


def facts(places: list[Place]) -> list[dict[str, object]]:
    return [{"id": p.id, "evidence": sorted(sources(p))} for p in places]


class DecisionLlmService:
    def __init__(self, provider: StructuredLlm) -> None:
        self.provider = provider

    async def filter_foods(self, places: list[Place], request: DecisionRequest) -> list[Place]:
        conditions = request.preferences
        if not places or not (conditions.allowed_foods or conditions.excluded_foods):
            return places
        result = await self.provider.structured(
            FoodAssessments,
            FILTER,
            {
                "allowedFoods": conditions.allowed_foods,
                "excludedFoods": conditions.excluded_foods,
                "places": facts(places),
            },
        )
        if len(result.places) != len(places) or {a.place_id for a in result.places} != {
            p.id for p in places
        }:
            raise AppError("LLM_INVALID_OUTPUT", "候选食物评估不完整", 502)
        by_id = {a.place_id: a for a in result.places}
        kept = []
        for p in places:
            assessment = by_id[p.id]
            for checks, terms in (
                (assessment.allowed, conditions.allowed_foods),
                (assessment.excluded, conditions.excluded_foods),
            ):
                if len(checks) != len(set(terms)) or {c.term for c in checks} != set(terms):
                    raise AppError("LLM_INVALID_OUTPUT", "食物条件评估不完整", 502)
                for check in checks:
                    if not set(check.evidence) <= sources(p) or (
                        check.status != "unknown" and not check.evidence
                    ):
                        raise AppError("LLM_INVALID_OUTPUT", "食物匹配依据无效", 502)
            if assessment.allowed and not any(c.status == "match" for c in assessment.allowed):
                continue
            if any(c.status != "mismatch" for c in assessment.excluded):
                continue
            kept.append(p)
        return kept

    async def rerank(
        self,
        places: list[Place],
        request: DecisionRequest,
        action: str = "",
        old_cuisines: list[str] | None = None,
    ) -> list[Place]:
        if not places:
            return places
        result = await self.provider.structured(
            Ranking,
            RERANK,
            {
                "requestText": request.request_text,
                "mealPeriod": request.meal_period,
                "partySize": request.party_size,
                "additionalGoal": "优先不同于之前菜系的餐厅"
                if action == "differentCuisine"
                else "",
                "previousCuisines": old_cuisines or [],
                "places": facts(places),
            },
        )
        validate_ranking(result, places)
        by_id = {item.place_id: item for item in result.places}
        ranked = []
        for p in places:
            match = by_id[p.id]
            total = round(p.score * 0.3 + match.score * 0.7, 2)
            ranked.append(
                p.model_copy(
                    update={
                        "score": total,
                        "score_breakdown": {
                            **p.score_breakdown,
                            "base": p.score,
                            "request_match": match.score,
                            "total": total,
                        },
                        "reason": "偏好匹配依据：" + "；".join(match.evidence)
                        if match.score > 0
                        else "",
                    }
                )
            )
        return sort_places(ranked)
