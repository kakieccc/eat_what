from decimal import Decimal

from pydantic.alias_generators import to_camel

from app.modules.preferences.models import Preference
from app.modules.preferences.schemas import (
    AccountPreferences,
    Budget,
    LearnedPreferences,
    LearningStatus,
    PreferenceOverrides,
    PreferencesResponse,
)


def builtin_defaults() -> AccountPreferences:
    return AccountPreferences(budget_per_person=Budget(min=Decimal("20"), max=Decimal("60")))


def learned_values(result: LearnedPreferences) -> dict[str, object]:
    values: dict[str, object] = {}
    if result.budget_per_person:
        values["budget_per_person"] = result.budget_per_person[0].value.model_dump(mode="json")
    if result.radius_meters:
        values["radius_meters"] = result.radius_meters[0].value
    if result.soft_preferences:
        values["request_text"] = "；".join(item.text for item in result.soft_preferences)
    return values


def preferences_from_row(row: Preference | None) -> PreferencesResponse:
    values = builtin_defaults().model_dump(mode="json")
    sources = {key: "builtin" for key in values}
    overrides = PreferenceOverrides.model_validate(row.overrides if row else {})
    if row and row.learned:
        for key, value in learned_values(LearnedPreferences.model_validate(row.learned)).items():
            values[key] = value
            sources[key] = "learned"
    for key, value in overrides.model_dump(mode="json", exclude_unset=True).items():
        values[key] = value
        sources[key] = "manual"
    count = row.meal_count if row else 0
    return PreferencesResponse.model_validate({
        "defaults": values, "sources": {to_camel(key): value for key, value in sources.items()},
        "overrides": overrides, "revision": row.revision if row else 0,
        "learning": LearningStatus(
            enabled=row.learning_enabled if row else False,
            meal_count=count, status=row.learning_status if row else "idle",
            last_success_at=row.last_success_at if row else None,
            next_learning_at=10 if count < 10 else (count // 5 + 1) * 5,
        ),
    })
