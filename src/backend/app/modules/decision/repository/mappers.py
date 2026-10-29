from app.modules.decision.models import DecisionRun, PlaceCandidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.places.schemas import Place


def request_for_run(run: DecisionRun) -> DecisionRequest:
    return DecisionRequest.model_validate(run.effective_preferences)


def place_from_candidate(candidate: PlaceCandidate) -> Place:
    return Place.model_validate(
        {**candidate.place_snapshot, "candidate_id": candidate.id, "rank": candidate.rank}
    )
