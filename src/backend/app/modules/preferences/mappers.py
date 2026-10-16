from app.modules.preferences.models import Preference
from app.modules.preferences.schemas import Budget, Preferences


def preferences_from_row(row: Preference | None) -> Preferences:
    if row is None:
        return Preferences()
    return Preferences(
        budget_per_person=Budget(
            min=row.typical_budget_per_person_min, max=row.typical_budget_per_person_max
        ),
        radius_meters=row.typical_radius_meters,
        allowed_foods=list(row.allowed_foods),
        preferred_foods=list(row.preferred_foods),
        excluded_foods=list(row.excluded_foods),
        soft_preferences=list(row.preferred_tags),
    )
