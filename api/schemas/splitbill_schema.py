from datetime import datetime
from typing import Optional
from pydantic import (
    BaseModel,
    EmailStr,
    StringConstraints,
)
from typing_extensions import Annotated
from decimal import Decimal
from enum import StrEnum

from api.models.models import ExpenseTypeEnum, StatusEnum


class TypeEnum(StrEnum):
    equal = "equal"
    percentage = "percentage"
    custom = "custom"


# ---------- EXPENSES ----------
class ExpenseAssignmentCreateSchema(BaseModel):
    member_id: int
    share_amount: Optional[Decimal]

    model_config = {"from_attributes": True}


class ExpenseAssignmentViewSchema(ExpenseAssignmentCreateSchema):
    pass


class ExpenseCreateSchema(BaseModel):
    title: str
    amount: Decimal
    type: ExpenseTypeEnum
    paid_by_id: int
    splitbill_id: int
    assignments: Optional[list[ExpenseAssignmentCreateSchema]] = None


class ExpenseReadSchema(BaseModel):
    id: int
    title: str
    amount: Decimal
    type: ExpenseTypeEnum
    date_created: datetime
    paid_by_id: int
    splitbill_id: int
    assignments: list[ExpenseAssignmentViewSchema]

    model_config = {"from_attributes": True}


class ExpenseUpdateSchema(BaseModel):
    title: Optional[str]
    amount: Optional[Decimal]
    type: Optional[ExpenseTypeEnum]
    paid_by_id: Optional[int]
    assignments: Optional[list[ExpenseAssignmentViewSchema]]

    model_config = {"from_attributes": True}


# ---------- MONEY GIVEN ----------
class MoneyGivenBaseSchema(BaseModel):
    title: str
    amount: Decimal


class MoneyGivenCreateSchema(MoneyGivenBaseSchema):
    given_by: int
    given_to: int
    splitbill_id: int


class MoneyGivenReadSchema(MoneyGivenBaseSchema):
    id: int
    given_by: int
    given_to: int
    splitbill_id: int
    date_created: datetime

    model_config = {"from_attributes": True}


# ---------- COMMENTS ----------
class CommentBaseSchema(BaseModel):
    text: Annotated[str, StringConstraints(min_length=10, max_length=500)]


class CommentCreateSchema(CommentBaseSchema):
    author_id: int
    splitbill_id: int


class CommentReadSchema(CommentBaseSchema):
    id: int
    date_created: datetime
    author_id: int
    splitbill_id: int

    model_config = {"from_attributes": True}


# ---------- BALANCES ----------
class BalanceCreateSchema(BaseModel):
    from_member_id: int
    to_member_id: int
    splitbill_id: int
    amount: Decimal


class BalanceReadSchema(BaseModel):
    id: int
    amount: Decimal
    from_member_id: int
    to_member_id: int
    status: StatusEnum

    model_config = {"from_attributes": True}


# ---------- SplitBill -----------


class PendingUserViewSchema(BaseModel):
    id: int
    email: Optional[str]
    alias: Optional[str]
    invited_at: datetime

    model_config = {"from_attributes": True}


class SplitBillMemberBaseSchema(BaseModel):
    email: Optional[EmailStr] = None
    alias: Optional[str] = None

    # @field_validator("email", mode="before")
    # @classmethod
    # def require_email_or_alias(cls, v, info):
    #     alias = info.data.get("alias")
    #     if not v and not alias:
    #         raise ValueError("At least one of 'email' or 'alias' must be provided")
    #     return v


class SplitBillMemberCreateSchema(SplitBillMemberBaseSchema):
    pass


class SplitBillMemberReadSchema(BaseModel):
    id: int
    email: Optional[EmailStr]
    alias: Optional[str]
    splitbill_id: int
    user_id: Optional[int]
    pending_user_id: Optional[int]
    invited_by: Optional[int]

    model_config = {"from_attributes": True}


class SplitBillMemberUpdateSchema(BaseModel):
    id: int
    alias: Optional[str]
    email: Optional[EmailStr]


class SplitBillMemberRemoveSchema(BaseModel):
    id: int


class SplitBillBaseSchema(BaseModel):
    title: str
    currency: str


class SplitBillCreateSchema(SplitBillBaseSchema):
    owner_id: int
    status: StatusEnum = StatusEnum.active
    members: list[SplitBillMemberCreateSchema]


class SplitBillUpdateSchema(BaseModel):
    title: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[StatusEnum] = None


class SplitBillReadSchema(SplitBillBaseSchema):
    id: int
    date_created: datetime
    owner_id: int
    status: StatusEnum
    members: list[SplitBillMemberReadSchema]
    expenses: list[ExpenseReadSchema]
    money_given: list[MoneyGivenReadSchema]
    comments: list[CommentReadSchema]
    balances: list[BalanceReadSchema]

    model_config = {"from_attributes": True}
