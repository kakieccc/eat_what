from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class UserRecord:
    id: str
    username: str
    display_name: str
    password: str
    created_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    id: str
    user: UserRecord
    csrf_token: str
    expires_at: datetime


class AuthRepository(Protocol):
    async def consume_limit(self, key_hash: str, limit: int, seconds: int) -> None: ...
    async def register(
        self, username: str, display_name: str, password: str,
        token_hash: str, csrf_token: str, expires_at: datetime,
    ) -> UserRecord: ...
    async def by_username(self, username: str) -> UserRecord | None: ...
    async def create_session(
        self, user_id: str, token_hash: str, csrf_token: str, expires_at: datetime,
        *, expected_password_hash: str,
    ) -> None: ...
    async def session(self, token_hash: str) -> SessionRecord | None: ...
    async def update_display_name(self, user_id: str, display_name: str) -> UserRecord: ...
    async def change_password(
        self, user_id: str, session_id: str, password: str,
    ) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...


class PasswordHasher(Protocol):
    dummy_hash: str
    async def hash(self, password: str) -> str: ...
    async def verify(self, password: str, encoded: str) -> bool: ...
    async def aclose(self) -> None: ...
