from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.application.auth.ports import AuthRepository, PasswordHasher, UserRecord
from app.core.clock import now
from app.core.errors import AppError
from app.domain.users.models import UserProfile


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def profile(row: UserRecord) -> UserProfile:
    return UserProfile(
        id=row.id, username=row.username,
        display_name=row.display_name, created_at=row.created_at,
    )


@dataclass(frozen=True)
class AuthContext:
    user: UserProfile
    session_id: str
    csrf_token: str


@dataclass(frozen=True)
class SignedIn:
    user: UserProfile
    token: str
    csrf_token: str


class AuthService:
    def __init__(self, repository: AuthRepository, passwords: PasswordHasher) -> None:
        self.repository = repository
        self.passwords = passwords

    @staticmethod
    def _tokens() -> tuple[str, str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        return token, csrf, digest(token)

    async def register(
        self, username: str, password: str, display_name: str, ip: str
    ) -> SignedIn:
        username = username.lower()
        await self.repository.consume_limit(digest(f"register:{ip}"), 10, 3600)
        encoded = await self.passwords.hash(password)
        token, csrf, token_hash = self._tokens()
        user = await self.repository.register(
            username, display_name, encoded,
            token_hash, csrf, now() + timedelta(days=7),
        )
        return SignedIn(profile(user), token, csrf)

    async def login(self, username: str, password: str, ip: str) -> SignedIn:
        username = username.lower()
        await self.repository.consume_limit(digest(f"login-ip:{ip}"), 30, 900)
        await self.repository.consume_limit(digest(f"login-user:{username}"), 10, 900)
        user = await self.repository.by_username(username)
        encoded = user.password if user else self.passwords.dummy_hash
        verified = await self.passwords.verify(password, encoded)
        if user is None or not verified:
            raise AppError("INVALID_CREDENTIALS", "用户名或密码错误", 401)
        token, csrf, token_hash = self._tokens()
        await self.repository.create_session(
            user.id, token_hash, csrf, now() + timedelta(days=7)
        )
        return SignedIn(profile(user), token, csrf)

    async def authenticate(self, token: str | None) -> AuthContext:
        if not token:
            raise AppError("AUTH_REQUIRED", "请先登录", 401)
        row = await self.repository.session(digest(token))
        if row is None or row.expires_at <= now():
            raise AppError("AUTH_REQUIRED", "登录状态已失效，请重新登录", 401)
        return AuthContext(profile(row.user), row.id, row.csrf_token)

    def verify_csrf(self, context: AuthContext, token: str | None) -> None:
        if not token or not hmac.compare_digest(token, context.csrf_token):
            raise AppError("CSRF_FAILED", "请求校验失败，请刷新页面", 403)

    async def update_display_name(self, context: AuthContext, name: str) -> UserProfile:
        return profile(await self.repository.update_display_name(context.user.id, name))

    async def change_password(
        self, context: AuthContext, current_password: str, new_password: str
    ) -> SignedIn:
        user = await self.repository.by_username(context.user.username)
        if user is None or not await self.passwords.verify(current_password, user.password):
            raise AppError("INVALID_CREDENTIALS", "当前密码错误", 401)
        encoded = await self.passwords.hash(new_password)
        token, csrf, token_hash = self._tokens()
        await self.repository.change_password(
            context.user.id, context.session_id, encoded,
            token_hash, csrf, now() + timedelta(days=7),
        )
        return SignedIn(context.user, token, csrf)

    async def logout(self, context: AuthContext) -> None:
        await self.repository.delete_session(context.session_id)
