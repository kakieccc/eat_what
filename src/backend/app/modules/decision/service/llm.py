from app.modules.decision.ports import StructuredLlm
from app.modules.decision.rules.llm import (
    evidence,
    validate_explanations,
    validate_intent,
    validate_ranking,
)
from app.modules.decision.schemas import Explanations, Intent, Ranking
from app.modules.decision.workflow.prompts.explain import PROMPT as EXPLAIN
from app.modules.decision.workflow.prompts.parse import PROMPT as PARSE
from app.modules.decision.workflow.prompts.rerank import PROMPT as RERANK
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import CUISINES, Preferences


class DecisionLlmService:
    def __init__(self, provider: StructuredLlm) -> None:
        self.provider = provider

    async def parse_intent(self, text: str) -> Intent:
        intent = await self.provider.structured(
            Intent, PARSE, {"text": text, "allowedCuisines": CUISINES}
        )
        validate_intent(intent)
        return intent

    async def rerank(self, places: list[Place], preferences: Preferences) -> list[Place]:
        result = await self.provider.structured(
            Ranking,
            RERANK,
            {
                "preferences": preferences.model_dump(
                    mode="json", exclude={"request_text", "origin"}
                ),
                "places": [{"id": p.id, "name": p.name, "evidence": evidence(p)} for p in places],
            },
        )
        validate_ranking(result, places)
        by_id = {p.id: p for p in places}
        return [by_id[key] for key in result.place_ids]

    async def explain(self, places: list[Place]) -> list[Place]:
        result = await self.provider.structured(
            Explanations, EXPLAIN, [{"id": p.id, "evidence": evidence(p)} for p in places]
        )
        reasons = validate_explanations(result, places)
        return [p.model_copy(update={"reason": reasons[p.id]}) for p in places]
