from datetime import datetime
from uuid import UUID

from app.core.models import Model


class PlaceChoiceRequest(Model):
    candidate_id: UUID


class ChoiceSnapshot(Model):
    id: str
    candidate_id: str
    decision_run_id: str
    selected_at: datetime
