from app.modules.preferences.models import Preference
from app.modules.preferences.schemas import Budget, Preferences


def preferences_from_row(row: Preference | None) -> Preferences:
    if row is None:
        return Preferences()
    return Preferences(
        budget_per_person=Budget(
            min=row.typical_budget_per_person_min, max=row.typical_budget_per_person_max
        ),
        max_walking_minutes=row.typical_max_walking_minutes or 15,
        preferred_cuisines=list(row.preferred_cuisines),
        excluded_cuisines=list(row.excluded_cuisines),
        desired_tags=list(row.preferred_tags),
    )
