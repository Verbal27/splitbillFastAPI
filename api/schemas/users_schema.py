from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, StringConstraints
from typing_extensions import Annotated

from api.models.models import UserStatusEnum

Username = Annotated[str, StringConstraints(min_length=3, max_length=20)]
Password = Annotated[str, StringConstraints(min_length=8)]


class UserBaseSchema(BaseModel):
    username: str
    email: EmailStr
    status: UserStatusEnum


class UserCreateSchema(BaseModel):
    username: Username
    email: EmailStr
    password: Password
    status: UserStatusEnum = UserStatusEnum.pending


class UserReadSchema(UserBaseSchema):
    id: int
    username: str
    email: str
    status: UserStatusEnum
    date_joined: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class UserUpdateSchema(BaseModel):
    username: Optional[Username] = None
    email: Optional[EmailStr] = None
    hashed_password: Optional[Password] = None
