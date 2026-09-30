from datetime import datetime

from pydantic import Field, field_validator

from app.core.models import Model


class UserProfile(Model):
    id: str
    username: str
    display_name: str
    created_at: datetime


class RegisterRequest(Model):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("昵称不能为空")
        return result


class LoginRequest(Model):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    password: str


class ProfileUpdateRequest(Model):
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("昵称不能为空")
        return result


class ChangePasswordRequest(Model):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AuthPayload(Model):
    user: UserProfile
    csrf_token: str
