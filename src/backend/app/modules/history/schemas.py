from __future__ import annotations

from datetime import datetime

from app.core.models import Model
from app.modules.decision.schemas import DecisionRequest
from app.modules.places.schemas import Place

HistoryCursor = tuple[datetime, str]


class HistoryChoice(Model):
    id: str
    place: Place
    decision_run_id: str


class HistoryItem(Model):
    id: str
    created_at: datetime
    request: DecisionRequest
    choice: HistoryChoice


class HistoryPage(Model):
    items: list[HistoryItem]
    next_cursor: str | None = None
