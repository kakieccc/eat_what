from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import uid
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.repository.mappers import place_from_candidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.preferences.mappers import preferences_from_row
from app.modules.preferences.models import Preference, PreferenceSample
from app.modules.preferences.ports import MealEvidence
from app.modules.preferences.schemas import (
    AccountPreferences,
    LearnedPreferences,
    PreferencesResponse,
    PreferencesUpdate,
    PrefillSnapshot,
)
from app.modules.task.errors import LostTaskLease
from app.modules.task.types import TaskClaim


async def locked_preference(session: AsyncSession, user_id: str) -> Preference:
    await session.execute(insert(Preference).values(user_id=user_id).on_conflict_do_nothing(
        index_elements=[Preference.user_id]
    ))
    row = await session.scalar(select(Preference).where(
        Preference.user_id == user_id
    ).with_for_update())
    assert row is not None
    return row


async def record_meal(
    session: AsyncSession, user_id: str, choice_id: str, candidate_id: str,
) -> None:
    candidate = await session.get(PlaceCandidate, candidate_id)
    assert candidate is not None
    run = await session.get(DecisionRun, candidate.decision_run_id)
    assert run is not None
    discovery = await session.get(DiscoverySession, run.discovery_session_id)
    assert discovery is not None
    # Flows opened before the migration have no trustworthy prefill provenance.
    if discovery.prefill_snapshot is None:
        return
    if await session.scalar(select(PreferenceSample.id).where(
        PreferenceSample.discovery_session_id == discovery.id
    )):
        return
    prefill = PrefillSnapshot.model_validate(discovery.prefill_snapshot)
    final = DecisionRequest.model_validate(run.effective_preferences)
    final_preferences = AccountPreferences(
        **final.preferences.model_dump(), request_text=final.request_text
    )
    conditions = final_preferences.model_dump(mode="json")
    active = {key: value for key, value in conditions.items()
              if getattr(final_preferences, key) != getattr(prefill.values, key)}
    row = await locked_preference(session, user_id)
    row.meal_count += 1
    place = place_from_candidate(candidate)
    session.add(PreferenceSample(
        user_id=user_id, choice_id=choice_id, discovery_session_id=discovery.id,
        meal_number=row.meal_count, prefill_snapshot=prefill.model_dump(mode="json"),
        active_changes=active, final_conditions=conditions, request_text=final.request_text,
        restaurant_facts={"category_name": place.category_name,
                          "cuisine_types": place.cuisine_types},
    ))
    if row.meal_count >= 10 and row.meal_count % 5 == 0:
        row.requested_count = row.meal_count
        if row.learning_status != "running":
            row.learning_status = "queued"


class PreferencesRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def get(self, user_id: str) -> PreferencesResponse:
        async with self.sessions() as session:
            row = await session.scalar(select(Preference).where(Preference.user_id == user_id))
            return preferences_from_row(row)

    async def save(self, user_id: str, update: PreferencesUpdate) -> PreferencesResponse:
        async with self.sessions.begin() as session:
            row = await locked_preference(session, user_id)
            if row.revision != update.revision:
                raise AppError("PREFERENCE_CONFLICT", "偏好已更新，请重新读取后再保存", 409)
            row.overrides = update.overrides.model_dump(mode="json", exclude_unset=True)
            row.revision += 1
            result = preferences_from_row(row)
        return result

    async def claim(self, lease_seconds: int) -> TaskClaim | None:
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Preference).where(
                Preference.learning_status.in_(["queued", "running"]),
                Preference.requested_count > Preference.attempted_count,
                or_(Preference.lease_until.is_(None), Preference.lease_until < now()),
            ).order_by(Preference.updated_at, Preference.id).with_for_update(skip_locked=True).limit(1))
            if row is None:
                return None
            row.lease_token = uid()
            row.lease_until = now() + timedelta(seconds=lease_seconds)
            row.claimed_count = row.requested_count
            row.learning_status = "running"
            return TaskClaim(row.id, row.lease_token)

    async def _claimed(self, session: AsyncSession, claim: TaskClaim) -> Preference:
        row = await session.scalar(select(Preference).where(
            Preference.id == claim.task_id, Preference.lease_token == claim.lease_token,
            Preference.lease_until > now(), Preference.learning_status == "running",
        ).with_for_update())
        if row is None:
            raise LostTaskLease(claim.task_id)
        return row

    async def renew(self, claim: TaskClaim, lease_seconds: int) -> None:
        async with self.sessions.begin() as session:
            row = await self._claimed(session, claim)
            row.lease_until = now() + timedelta(seconds=lease_seconds)

    async def samples(self, claim: TaskClaim) -> list[MealEvidence]:
        async with self.sessions.begin() as session:
            row = await self._claimed(session, claim)
            samples = list((await session.scalars(select(PreferenceSample).where(
                PreferenceSample.user_id == row.user_id,
                PreferenceSample.meal_number <= row.claimed_count,
            ).order_by(PreferenceSample.meal_number.desc()).limit(20))).all())
            return [MealEvidence(
                id=sample.id, meal_number=sample.meal_number, active_changes=sample.active_changes,
                request_text=sample.request_text, restaurant_facts=sample.restaurant_facts,
            ) for sample in samples[::-1]]

    async def finish(self, claim: TaskClaim, result: LearnedPreferences | None) -> None:
        async with self.sessions.begin() as session:
            row = await self._claimed(session, claim)
            row.attempted_count = row.claimed_count
            if result is not None:
                row.learned = result.model_dump(mode="json")
                row.last_success_at = now()
                row.revision += 1
            row.learning_status = (
                "queued" if row.requested_count > row.attempted_count
                else "idle" if result is not None else "failed"
            )
            row.lease_token = None
            row.lease_until = None
