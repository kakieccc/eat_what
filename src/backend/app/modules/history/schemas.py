from __future__ import annotations

from datetime import datetime

from app.core.models import Model
from app.modules.places.schemas import Place
from app.modules.preferences.schemas import Preferences


class HistoryChoice(Model):
    id: str
    feedback: str
    place: Place
    decision_run_id: str


class HistoryItem(Model):
    id: str
    created_at: datetime
    request: Preferences
    choices: list[HistoryChoice]


class HistoryPage(Model):
    items: list[HistoryItem]
    next_cursor: str | None = None


__all__ = ["HistoryChoice", "HistoryItem", "HistoryPage", "Place", "Preferences"]
