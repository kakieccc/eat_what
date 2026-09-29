from __future__ import annotations

from datetime import datetime

from app.domain.base import Model
from app.domain.places.models import Place
from app.domain.preferences.models import Preferences


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
