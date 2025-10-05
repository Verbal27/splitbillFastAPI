from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, StringConstraints
from typing_extensions import Annotated

from api.models.models import UserStatusEnum

Username = Annotated[str, StringConstraints(min_length=3, max_length=20)]
Password = Annotated[str, StringConstraints(min_length=8)]


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    sub: int | None = None


class UserLoginSchema(BaseModel):
    email: EmailStr
    password: Password


class UserBaseSchema(BaseModel):
    username: str
    email: EmailStr
    status: UserStatusEnum


class UserCreateSchema(BaseModel):
    username: Username
    email: EmailStr
    password: Password


class UserReadSchema(UserBaseSchema):
    id: int
    date_joined: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class UserUpdateSchema(BaseModel):
    username: Optional[Username] = None
    email: Optional[EmailStr] = None
    password: Optional[Password] = None


class UserPasswordUpdateSchema(BaseModel):
    password: Password


class PasswordResetSchema(BaseModel):
    token: str
    user_id: int
