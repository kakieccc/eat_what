from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.config import settings
from app.core.errors import AppError
from app.core.ids import uid
from app.modules.decision.models import DecisionRun, DiscoverySession, PlaceCandidate
from app.modules.decision.repository.mappers import place_from_candidate
from app.modules.decision.schemas import DecisionRequest
from app.modules.preferences.mappers import preferences_from_row
from app.modules.preferences.models import Preference, PreferenceSample
from app.modules.preferences.ports import MealEvidence
from app.modules.preferences.schemas import (
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
    if await session.scalar(select(PreferenceSample.id).where(
        PreferenceSample.discovery_session_id == discovery.id
    )):
        return
    prefill = PrefillSnapshot.model_validate(discovery.prefill_snapshot)
    final = DecisionRequest.model_validate(run.effective_preferences)
    conditions = {**final.preferences.model_dump(mode="json"), "request_text": final.request_text}
    baseline = prefill.values.model_dump(mode="json")
    # Accepting prefilled defaults is not another active expression of the same preference.
    active = {key: value for key, value in conditions.items()
              if value != baseline[key]}
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
    if (
        row.learning_enabled
        and row.meal_count >= settings.preference_learning_min_meals
        and row.meal_count % settings.preference_learning_interval == 0
    ):
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
                raise AppError("PREFERENCE_CONFLICT", "偏好已更新，请刷新页面后再保存", 409)
            row.overrides = update.overrides.model_dump(mode="json", exclude_unset=True)
            row.revision += 1
            result = preferences_from_row(row)
        return result

    async def set_learning(self, user_id: str, enabled: bool) -> PreferencesResponse:
        async with self.sessions.begin() as session:
            row = await locked_preference(session, user_id)
            if row.learning_enabled == enabled:
                return preferences_from_row(row)
            # The switch leaves defaults unchanged, so an open editor keeps its valid revision.
            row.learning_enabled = enabled
            if enabled:
                eligible_count = row.meal_count // settings.preference_learning_interval * settings.preference_learning_interval
                if eligible_count >= settings.preference_learning_min_meals and eligible_count > row.attempted_count:
                    row.requested_count = eligible_count
                    row.learning_status = "queued"
            else:
                row.requested_count = row.attempted_count
                row.learning_status = "idle"
                # Revoke running claims so a late result cannot write after learning is disabled.
                row.lease_token = None
                row.lease_until = None
            return preferences_from_row(row)

    @staticmethod
    def _pending() -> Select[tuple[Preference]]:
        return select(Preference).where(
            Preference.learning_enabled.is_(True),
            Preference.learning_status.in_(["queued", "running"]),
            Preference.requested_count > Preference.attempted_count,
            or_(Preference.lease_until.is_(None), Preference.lease_until < now()),
        ).order_by(Preference.updated_at, Preference.id)

    async def pending_ids(self) -> list[str]:
        async with self.sessions() as session:
            return list((await session.scalars(self._pending().with_only_columns(Preference.id))).all())

    async def claim(self, lease_seconds: int, *, preference_id: str | None = None) -> TaskClaim | None:
        statement = self._pending()
        if preference_id is not None:
            statement = statement.where(Preference.id == preference_id)
        async with self.sessions.begin() as session:
            row = await session.scalar(statement.with_for_update(skip_locked=True).limit(1))
            if row is None:
                return None
            row.lease_token = uid()
            row.lease_until = now() + timedelta(seconds=lease_seconds)
            # Meals added during learning belong to a later batch, not this evidence snapshot.
            row.claimed_count = row.requested_count
            row.learning_status = "running"
            return TaskClaim(row.id, row.lease_token)

    async def _claimed(self, session: AsyncSession, claim: TaskClaim) -> Preference:
        row = await session.scalar(select(Preference).where(
            Preference.learning_enabled.is_(True),
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
            ).order_by(PreferenceSample.meal_number.desc()).limit(settings.preference_learning_sample_limit))).all())
            return [MealEvidence(
                id=sample.id, meal_number=sample.meal_number, active_changes=sample.active_changes,
                request_text=sample.request_text, restaurant_facts=sample.restaurant_facts,
            ) for sample in samples[::-1]]

    async def finish(self, claim: TaskClaim, result: LearnedPreferences | None) -> None:
        async with self.sessions.begin() as session:
            row = await self._claimed(session, claim)
            # Failed learning waits for new meal evidence instead of retrying the same batch daily.
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
