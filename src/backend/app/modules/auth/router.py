from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from app.api.dependencies import ContainerDependency, SettingsDependency
from app.api.errors import error_responses
from app.api.schemas import Envelope
from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.dependencies import (
    CurrentUserDependency,
    MutationUserDependency,
)
from app.modules.auth.schemas import (
    AuthPayload,
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    UserProfile,
)
from app.modules.auth.service import SignedIn

router = APIRouter(prefix="/auth", tags=["auth"])


def cookie(response: Response, signed_in: SignedIn, settings: Settings) -> None:
    response.set_cookie(
        "food_session", signed_in.token,
        max_age=settings.auth_session_days * 24 * 3600,
        path="/", secure=True,
        httponly=True, samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def check_intent(value: str | None) -> None:
    if value != "web":
        raise AppError("CSRF_FAILED", "请求校验失败", 403)


@router.post("/register", status_code=201, responses=error_responses(403, 409, 422, 429, 503))
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    services: ContainerDependency,
    settings: SettingsDependency,
    intent: Annotated[str | None, Header(alias="X-Auth-Intent")] = None,
) -> Envelope[AuthPayload]:
    check_intent(intent)
    signed = await services.auth.register(
        body.username, body.password, body.display_name,
        request.client.host if request.client else "unknown",
    )
    cookie(response, signed, settings)
    return Envelope(data=AuthPayload(user=signed.user, csrf_token=signed.csrf_token))


@router.post("/login", responses=error_responses(401, 403, 422, 429, 503))
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    services: ContainerDependency,
    settings: SettingsDependency,
    intent: Annotated[str | None, Header(alias="X-Auth-Intent")] = None,
) -> Envelope[AuthPayload]:
    check_intent(intent)
    signed = await services.auth.login(
        body.username, body.password, request.client.host if request.client else "unknown"
    )
    cookie(response, signed, settings)
    return Envelope(data=AuthPayload(user=signed.user, csrf_token=signed.csrf_token))


@router.get("/me", responses=error_responses(401, 503))
async def me(user: CurrentUserDependency) -> Envelope[AuthPayload]:
    return Envelope(data=AuthPayload(user=user.user, csrf_token=user.csrf_token))


@router.patch("/me", responses=error_responses(401, 403, 422, 503))
async def update_me(
    body: ProfileUpdateRequest, user: MutationUserDependency, services: ContainerDependency
) -> Envelope[UserProfile]:
    return Envelope(data=await services.auth.update_display_name(user, body.display_name))


@router.post("/change-password", responses=error_responses(401, 403, 422, 429, 503))
async def change_password(
    body: ChangePasswordRequest, response: Response,
    user: MutationUserDependency, services: ContainerDependency,
) -> Envelope[dict[str, bool]]:
    await services.auth.change_password(
        user, body.current_password, body.new_password
    )
    response.delete_cookie("food_session", path="/")
    response.headers["Cache-Control"] = "no-store"
    return Envelope(data={"loggedOut": True})


@router.post("/logout", responses=error_responses(401, 403, 422, 503))
async def logout(
    response: Response, user: MutationUserDependency, services: ContainerDependency
) -> Envelope[dict[str, bool]]:
    await services.auth.logout(user)
    response.delete_cookie("food_session", path="/")
    response.headers["Cache-Control"] = "no-store"
    return Envelope(data={"loggedOut": True})
