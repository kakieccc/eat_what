from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now
from app.core.errors import AppError
from app.core.ids import lock_id
from app.modules.auth.models import AuthRateLimit, AuthSession, User
from app.modules.auth.ports import SessionRecord, UserRecord


def record(row: User) -> UserRecord:
    return UserRecord(row.id, row.username, row.display_name, row.password, row.created_at)


class SqlAuthRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def consume_limit(self, key_hash: str, limit: int, seconds: int) -> None:
        current = now()
        async with self.sessions.begin() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id(key_hash)}
            )
            row = await session.scalar(
                select(AuthRateLimit).where(AuthRateLimit.key_hash == key_hash).with_for_update()
            )
            if row is None:
                session.add(AuthRateLimit(key_hash=key_hash, window_started_at=current, attempts=1))
                return
            if row.window_started_at + timedelta(seconds=seconds) <= current:
                row.window_started_at = current
                row.attempts = 1
                return
            if row.attempts >= limit:
                raise AppError("RATE_LIMITED", "请求过于频繁，请稍后再试", 429, True)
            row.attempts += 1

    async def register(
        self, username: str, display_name: str, password: str,
        token_hash: str, csrf_token: str, expires_at: datetime,
    ) -> UserRecord:
        try:
            async with self.sessions.begin() as session:
                user = User(
                    username=username, display_name=display_name, password=password
                )
                session.add(user)
                await session.flush()
                session.add(AuthSession(
                    user_id=user.id, token_hash=token_hash,
                    csrf_token=csrf_token, expires_at=expires_at,
                ))
                await session.flush()
                return record(user)
        except IntegrityError as error:
            raise AppError("USERNAME_TAKEN", "用户名已被使用", 409) from error

    async def by_username(self, username: str) -> UserRecord | None:
        async with self.sessions() as session:
            row = await session.scalar(select(User).where(User.username == username))
            return record(row) if row else None

    async def create_session(
        self, user_id: str, token_hash: str, csrf_token: str, expires_at: datetime
    ) -> None:
        async with self.sessions.begin() as session:
            session.add(AuthSession(
                user_id=user_id, token_hash=token_hash,
                csrf_token=csrf_token, expires_at=expires_at,
            ))

    async def session(self, token_hash: str) -> SessionRecord | None:
        async with self.sessions() as session:
            row = await session.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_hash)
            )
            if row is None:
                return None
            user = await session.get(User, row.user_id)
            return SessionRecord(row.id, record(user), row.csrf_token, row.expires_at) if user else None

    async def update_display_name(self, user_id: str, display_name: str) -> UserRecord:
        async with self.sessions.begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                raise AppError("AUTH_REQUIRED", "请重新登录", 401)
            user.display_name = display_name
            await session.flush()
            return record(user)

    async def change_password(
        self, user_id: str, session_id: str, password: str,
        token_hash: str, csrf_token: str, expires_at: datetime,
    ) -> None:
        async with self.sessions.begin() as session:
            user = await session.get(User, user_id, with_for_update=True)
            active = await session.scalar(select(AuthSession.id).where(
                AuthSession.id == session_id, AuthSession.user_id == user_id,
                AuthSession.expires_at > now(),
            ))
            if user is None or active is None:
                raise AppError("AUTH_REQUIRED", "请重新登录", 401)
            user.password = password
            await session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
            session.add(AuthSession(
                user_id=user_id, token_hash=token_hash,
                csrf_token=csrf_token, expires_at=expires_at,
            ))

    async def delete_session(self, session_id: str) -> None:
        async with self.sessions.begin() as session:
            await session.execute(delete(AuthSession).where(AuthSession.id == session_id))
