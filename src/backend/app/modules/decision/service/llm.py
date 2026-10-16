from app.core.errors import AppError
from app.modules.decision.ports import StructuredLlm
from app.modules.decision.rules.llm import (
    evidence,
    validate_explanations,
    validate_intent,
    validate_ranking,
)
from app.modules.decision.schemas import (
    DecisionIntent,
    DecisionRequest,
    Explanations,
    Intent,
    Ranking,
)
from app.modules.decision.workflow.prompts.explain import PROMPT as EXPLAIN
from app.modules.decision.workflow.prompts.parse import PROMPT as PARSE
from app.modules.decision.workflow.prompts.rerank import PROMPT as RERANK
from app.modules.places.schemas import Place


class DecisionLlmService:
    def __init__(self, provider: StructuredLlm) -> None:
        self.provider = provider

    async def parse_intent(self, request: DecisionRequest) -> DecisionIntent:
        intent = await self.provider.structured(
            Intent, PARSE, request.model_dump(mode="json", by_alias=True)
        )
        validate_intent(intent, request)
        if intent.allergies:
            raise AppError(
                "ALLERGY_REQUIREMENT_UNVERIFIABLE", "当前数据无法核实过敏要求，请直接向餐厅确认", 422
            )
        effective = request.model_copy(update={"preferences": intent.preferences})
        return DecisionIntent(
            effective_request=effective,
            search_keywords=intent.search_keywords,
            unhandled_requirements=intent.unhandled_requirements,
            excluded_ingredients=intent.excluded_ingredients,
            allergies=intent.allergies,
        )

    async def rerank(
        self,
        places: list[Place],
        preferences: DecisionRequest,
        intent: DecisionIntent,
        action: str = "",
        old_cuisines: list[str] | None = None,
    ) -> list[Place]:
        if intent.allergies:
            raise AppError("ALLERGY_REQUIREMENT_UNVERIFIABLE", "当前数据无法核实过敏要求", 422)
        # POI data has no menu or ingredient evidence; never infer ingredient absence.
        if intent.excluded_ingredients:
            return []
        result = await self.provider.structured(
            Ranking,
            RERANK,
            {
                "action": action,
                "previousCuisines": old_cuisines or [],
                "request": preferences.model_dump(mode="json", by_alias=True),
                "places": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "category": p.category_name,
                        "tags": p.tags,
                        "warnings": p.warnings,
                        "score": p.score,
                        "evidence": evidence(p),
                    }
                    for p in places
                ],
            },
        )
        validate_ranking(result, places)
        by_id = {p.id: p for p in places}
        if len(result.assessments) != len(places) or {
            a.place_id for a in result.assessments
        } != set(by_id):
            raise AppError("LLM_INVALID_OUTPUT", "候选匹配结果无效", 502)
        assessments = {a.place_id: a for a in result.assessments}
        kept: list[Place] = []
        conditions = preferences.preferences
        for key in result.place_ids:
            p, assessment = by_id[key], assessments[key]
            sources = {p.name, p.category_name, *p.tags, *evidence(p)} - {""}
            for checks, terms in (
                (assessment.allowed, conditions.allowed_foods),
                (assessment.excluded, conditions.excluded_foods),
                (assessment.soft, conditions.soft_preferences),
            ):
                if len(checks) != len(set(terms)) or {c.term for c in checks} != set(terms):
                    raise AppError("LLM_INVALID_OUTPUT", "条件评估不完整", 502)
                for check in checks:
                    if not set(check.evidence) <= sources or (
                        check.status != "unknown" and not check.evidence
                    ):
                        raise AppError("LLM_INVALID_OUTPUT", "匹配依据无效", 502)
            if assessment.allowed and not any(c.status == "match" for c in assessment.allowed):
                continue
            if any(c.status != "mismatch" for c in assessment.excluded):
                continue
            matched = [c for c in assessment.soft if c.status == "match"]
            if assessment.soft and not matched:
                continue
            warnings = [w for w in p.warnings if w != "食物类型信息不足，无法确认符合限定要求"]
            for check in assessment.soft:
                if check.status != "match":
                    label = "尚无法确认" if check.status == "unknown" else "现有信息不匹配"
                    warnings.append(f"{check.term}：{label}")
            reasons = [
                f"根据{'、'.join(c.evidence)}，作为“{c.term}”偏好的候选（不代表具体菜品保证）"
                for c in matched
            ]
            kept.append(p.model_copy(update={
                "warnings": list(dict.fromkeys(warnings)),
                "reason": "；".join(reasons),
                "score_breakdown": {**p.score_breakdown, "soft_matches": float(len(matched))},
            }))
        return sorted(kept, key=lambda p: -p.score_breakdown["soft_matches"])

    async def explain(self, places: list[Place]) -> list[Place]:
        result = await self.provider.structured(
            Explanations, EXPLAIN, [{"id": p.id, "evidence": evidence(p)} for p in places]
        )
        reasons = validate_explanations(result, places)
        return [p.model_copy(update={"reason": "；".join(filter(None, [p.reason, reasons[p.id]]))}) for p in places]
