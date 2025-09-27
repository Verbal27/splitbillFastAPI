from sqlalchemy import (
    String,
    ForeignKey,
    Numeric,
    Enum as SAEnum,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal
from ..db.database import Base, intpk, created_at, updated_at
import enum


# ---------- ENUMS ----------
class UserStatusEnum(str, enum.Enum):
    active = "active"
    pending = "pending"


class StatusEnum(str, enum.Enum):
    active = "active"
    settled = "settled"


class ExpenseTypeEnum(str, enum.Enum):
    equal = "equal"
    percentage = "percentage"
    custom = "custom"


# ---------- USERS ----------
class UsersOrm(Base):
    __tablename__ = "users"

    id: Mapped[intpk]
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatusEnum] = mapped_column(
        SAEnum(UserStatusEnum, native_enum=False),
        nullable=False,
        default=UserStatusEnum.pending,
    )
    date_joined: Mapped[created_at] = mapped_column(server_default=func.now())
    activation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_updated: Mapped[updated_at]
    # Relationships
    splitbills: Mapped[list["SplitBillsOrm"]] = relationship(
        "SplitBillsOrm", back_populates="owner", cascade="all, delete-orphan"
    )
    members: Mapped[list["SplitBillMembersOrm"]] = relationship(
        "SplitBillMembersOrm",
        foreign_keys="SplitBillMembersOrm.user_id",
        back_populates="user",
    )
    invited_members: Mapped[list["SplitBillMembersOrm"]] = relationship(
        "SplitBillMembersOrm",
        foreign_keys="SplitBillMembersOrm.invited_by",
        back_populates="inviter",
    )
    password_resets: Mapped[list["PasswordResetOrm"]] = relationship(
        "PasswordResetOrm", back_populates="user", cascade="all, delete-orphan"
    )


# ---------- SPLITBILLS ----------
class SplitBillsOrm(Base):
    __tablename__ = "splitbills"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date_created: Mapped[created_at] = mapped_column(server_default=func.now())
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    owner: Mapped["UsersOrm"] = relationship("UsersOrm", back_populates="splitbills")

    members: Mapped[list["SplitBillMembersOrm"]] = relationship(
        "SplitBillMembersOrm", back_populates="splitbill", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["ExpensesOrm"]] = relationship(
        "ExpensesOrm", back_populates="splitbill", cascade="all, delete-orphan"
    )
    money_given: Mapped[list["MoneyGivenOrm"]] = relationship(
        "MoneyGivenOrm", back_populates="splitbill", cascade="all, delete-orphan"
    )
    comments: Mapped[list["CommentsOrm"]] = relationship(
        "CommentsOrm", back_populates="splitbill", cascade="all, delete-orphan"
    )
    balances: Mapped[list["BalancesOrm"]] = relationship(
        "BalancesOrm", back_populates="splitbill", cascade="all, delete-orphan"
    )

    status: Mapped[StatusEnum] = mapped_column(
        SAEnum(StatusEnum, native_enum=False),
        nullable=False,
        default=StatusEnum.active,
    )


# ---------- PENDING USERS ----------
class PendingUsersOrm(Base):
    __tablename__ = "pendingusers"

    id: Mapped[intpk]
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(50), nullable=True)
    invited_at: Mapped[created_at] = mapped_column(server_default=func.now())

    members: Mapped[list["SplitBillMembersOrm"]] = relationship(
        "SplitBillMembersOrm", back_populates="pending_user"
    )


# ---------- SPLITBILL MEMBERS ----------
class SplitBillMembersOrm(Base):
    __tablename__ = "splitbillmembers"
    __table_args__ = (
        UniqueConstraint("splitbill_id", "alias", name="uq_splitbill_alias"),
    )

    id: Mapped[intpk]
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(50), nullable=True)
    splitbill_id: Mapped[int] = mapped_column(ForeignKey("splitbills.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    pending_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("pendingusers.id"), nullable=True
    )
    invited_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relationships
    user: Mapped["UsersOrm"] = relationship(
        "UsersOrm", foreign_keys=[user_id], back_populates="members"
    )
    pending_user: Mapped["PendingUsersOrm"] = relationship(
        "PendingUsersOrm", foreign_keys=[pending_user_id], back_populates="members"
    )
    splitbill: Mapped["SplitBillsOrm"] = relationship(
        "SplitBillsOrm", back_populates="members"
    )
    inviter: Mapped["UsersOrm"] = relationship(
        "UsersOrm", foreign_keys=[invited_by], back_populates="invited_members"
    )

    expenses_paid: Mapped[list["ExpensesOrm"]] = relationship(
        "ExpensesOrm", back_populates="paid_by_member"
    )
    balances_from: Mapped[list["BalancesOrm"]] = relationship(
        "BalancesOrm",
        foreign_keys="BalancesOrm.from_member_id",
        back_populates="from_member",
    )
    balances_to: Mapped[list["BalancesOrm"]] = relationship(
        "BalancesOrm",
        foreign_keys="BalancesOrm.to_member_id",
        back_populates="to_member",
    )
    money_given_by: Mapped[list["MoneyGivenOrm"]] = relationship(
        "MoneyGivenOrm",
        foreign_keys="MoneyGivenOrm.given_by",
        back_populates="given_by_member",
    )
    money_given_to: Mapped[list["MoneyGivenOrm"]] = relationship(
        "MoneyGivenOrm",
        foreign_keys="MoneyGivenOrm.given_to",
        back_populates="given_to_member",
    )


# ---------- EXPENSES ----------
class ExpensesOrm(Base):
    __tablename__ = "expenses"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.0"))
    type: Mapped[ExpenseTypeEnum] = mapped_column(
        SAEnum(ExpenseTypeEnum, native_enum=False), nullable=False
    )
    date_created: Mapped[created_at] = mapped_column(server_default=func.now())

    paid_by_id: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    splitbill_id: Mapped[int] = mapped_column(
        ForeignKey("splitbills.id", ondelete="CASCADE")
    )

    splitbill: Mapped["SplitBillsOrm"] = relationship(
        "SplitBillsOrm", back_populates="expenses"
    )
    paid_by_member: Mapped["SplitBillMembersOrm"] = relationship(
        "SplitBillMembersOrm", back_populates="expenses_paid"
    )
    assignments: Mapped[list["ExpenseAssignmentOrm"]] = relationship(
        "ExpenseAssignmentOrm", back_populates="expense", cascade="all, delete-orphan"
    )


# ---------- EXPENSE ASSIGNMENTS ----------
class ExpenseAssignmentOrm(Base):
    __tablename__ = "expenseassignments"

    id: Mapped[intpk]
    share_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.0"), nullable=False
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE")
    )
    expense: Mapped["ExpensesOrm"] = relationship(
        "ExpensesOrm", back_populates="assignments"
    )

    member_id: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )


# ---------- MONEY GIVEN ----------
class MoneyGivenOrm(Base):
    __tablename__ = "moneygiven"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.0"))
    date_created: Mapped[created_at] = mapped_column(server_default=func.now())

    given_by: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    given_to: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    splitbill_id: Mapped[int] = mapped_column(
        ForeignKey("splitbills.id", ondelete="CASCADE")
    )

    splitbill: Mapped["SplitBillsOrm"] = relationship(
        "SplitBillsOrm", back_populates="money_given"
    )
    given_by_member: Mapped["SplitBillMembersOrm"] = relationship(
        "SplitBillMembersOrm", foreign_keys=[given_by], back_populates="money_given_by"
    )
    given_to_member: Mapped["SplitBillMembersOrm"] = relationship(
        "SplitBillMembersOrm", foreign_keys=[given_to], back_populates="money_given_to"
    )


# ---------- COMMENTS ----------
class CommentsOrm(Base):
    __tablename__ = "comments"

    id: Mapped[intpk]
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    date_created: Mapped[created_at] = mapped_column(server_default=func.now())

    author_id: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    splitbill_id: Mapped[int] = mapped_column(
        ForeignKey("splitbills.id", ondelete="CASCADE")
    )

    splitbill: Mapped["SplitBillsOrm"] = relationship(
        "SplitBillsOrm", back_populates="comments"
    )


# ---------- BALANCES ----------
class BalancesOrm(Base):
    __tablename__ = "balances"

    id: Mapped[intpk]
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.0"))

    from_member_id: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    to_member_id: Mapped[int] = mapped_column(
        ForeignKey("splitbillmembers.id", ondelete="CASCADE")
    )
    splitbill_id: Mapped[int] = mapped_column(
        ForeignKey("splitbills.id", ondelete="CASCADE")
    )

    status: Mapped[StatusEnum] = mapped_column(
        SAEnum(StatusEnum, native_enum=False),
        nullable=False,
        default=StatusEnum.active,
    )

    splitbill: Mapped["SplitBillsOrm"] = relationship(
        "SplitBillsOrm", back_populates="balances"
    )
    from_member: Mapped["SplitBillMembersOrm"] = relationship(
        "SplitBillMembersOrm",
        foreign_keys=[from_member_id],
        back_populates="balances_from",
    )
    to_member: Mapped["SplitBillMembersOrm"] = relationship(
        "SplitBillMembersOrm", foreign_keys=[to_member_id], back_populates="balances_to"
    )


class PasswordResetOrm(Base):
    __tablename__ = "passwordreset"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    user: Mapped["UsersOrm"] = relationship(
        "UsersOrm", back_populates="password_resets"
    )
