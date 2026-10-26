from typing import Annotated

from fastapi import Depends, Header, Request

from app.api.dependencies import ContainerDependency
from app.modules.auth.service import AuthContext


async def current_user(request: Request, services: ContainerDependency) -> AuthContext:
    return await services.auth.authenticate(request.cookies.get("food_session"))


async def mutation_user(
    services: ContainerDependency,
    user: Annotated[AuthContext, Depends(current_user)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    services.auth.verify_csrf(user, csrf_token)
    return user


CurrentUserDependency = Annotated[AuthContext, Depends(current_user)]
MutationUserDependency = Annotated[AuthContext, Depends(mutation_user)]
