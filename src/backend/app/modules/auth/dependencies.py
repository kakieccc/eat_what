from typing import Annotated

from fastapi import Depends, Header, Request

from app.api.dependencies import ContainerDependency
from app.modules.auth.service import AuthContext, AuthService


def get_auth_service(services: ContainerDependency) -> AuthService:
    return services.auth


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def current_user(request: Request, auth: AuthServiceDependency) -> AuthContext:
    return await auth.authenticate(request.cookies.get("food_session"))


async def mutation_user(
    auth: AuthServiceDependency,
    user: Annotated[AuthContext, Depends(current_user)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    auth.verify_csrf(user, csrf_token)
    return user


CurrentUserDependency = Annotated[AuthContext, Depends(current_user)]
MutationUserDependency = Annotated[AuthContext, Depends(mutation_user)]
