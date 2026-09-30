from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.location.schemas import Origin
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import Budget


def request_from_session(row: DiscoverySession) -> DecisionRequest:
    return DecisionRequest(
        origin=Origin(
            latitude=row.origin_latitude, longitude=row.origin_longitude, address=row.origin_address
        ),
        budget_per_person=Budget(min=row.budget_per_person_min, max=row.budget_per_person_max),
        max_walking_minutes=row.max_walking_minutes,
        radius_meters=row.radius_meters,
        preferred_cuisines=list(row.preferred_cuisines),
        excluded_cuisines=list(row.excluded_cuisines),
        desired_tags=list(row.desired_tags),
        meal_period=row.meal_period,
        party_size=row.party_size,
        open_now_preferred=row.open_now_preferred,
        request_text=row.request_text,
    )


def session_values(request: DecisionRequest) -> dict[str, object]:
    return {
        "origin_latitude": request.origin.latitude,
        "origin_longitude": request.origin.longitude,
        "origin_address": request.origin.address,
        "budget_per_person_min": request.budget_per_person.min,
        "budget_per_person_max": request.budget_per_person.max,
        "max_walking_minutes": request.max_walking_minutes,
        "radius_meters": request.radius_meters,
        "preferred_cuisines": request.preferred_cuisines,
        "excluded_cuisines": request.excluded_cuisines,
        "desired_tags": request.desired_tags,
        "meal_period": request.meal_period,
        "party_size": request.party_size,
        "open_now_preferred": request.open_now_preferred,
        "request_text": request.request_text,
        "normalized_preferences": request.model_dump(mode="json"),
    }


def request_for_run(run: DecisionRun, discovery: DiscoverySession) -> DecisionRequest:
    if run.effective_preferences:
        return DecisionRequest.model_validate(run.effective_preferences)
    return request_from_session(discovery)


def place_from_candidate(candidate: PlaceCandidate) -> Place:
    return Place.model_validate(
        {**candidate.place_snapshot, "candidate_id": candidate.id, "rank": candidate.rank}
    )
