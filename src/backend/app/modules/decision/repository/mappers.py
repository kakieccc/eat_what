from app.core.models import Model
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.rules.policies import WEIGHTS
from app.modules.decision.schemas import DecisionRequest
from app.modules.places.schemas import Place


def _read_snapshot[Snapshot: Model](schema: type[Snapshot], data: dict[str, object]) -> Snapshot:
    # Historical snapshots may include fields removed from the current contract.
    keys = set(schema.model_fields)
    keys.update(field.alias for field in schema.model_fields.values() if field.alias is not None)
    return schema.model_validate({key: value for key, value in data.items() if key in keys})


def request_from_session(row: DiscoverySession) -> DecisionRequest:
    return DecisionRequest.model_validate(row.request_snapshot)


def session_values(request: DecisionRequest) -> dict[str, object]:
    return {"request_snapshot": request.model_dump(mode="json")}


def request_for_run(run: DecisionRun, discovery: DiscoverySession) -> DecisionRequest:
    if run.effective_preferences:
        return _read_snapshot(DecisionRequest, run.effective_preferences)
    return request_from_session(discovery)


def place_from_candidate(candidate: PlaceCandidate) -> Place:
    place = _read_snapshot(
        Place, {**candidate.place_snapshot, "candidate_id": candidate.id, "rank": candidate.rank}
    )
    return place.model_copy(
        update={
            "score_breakdown": {
                key: value
                for key, value in place.score_breakdown.items()
                if key in WEIGHTS or key == "total"
            }
        }
    )
