from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.utils import (
    _apply_money_given_to_balances,
    calculate_balances,
    get_splitbill_view,
)


from ..db.database import get_session
from ..models.models import (
    CommentsOrm,
    ExpenseAssignmentOrm,
    ExpenseTypeEnum,
    MoneyGivenOrm,
    SplitBillsOrm,
    SplitBillMembersOrm,
    ExpensesOrm,
    PendingUsersOrm,
    UsersOrm,
)
from ..schemas.splitbill_schema import (
    CommentCreateSchema,
    CommentReadSchema,
    ExpenseCreateSchema,
    ExpenseReadSchema,
    MoneyGivenCreateSchema,
    MoneyGivenReadSchema,
    SplitBillCreateSchema,
    SplitBillReadSchema,
)


router = APIRouter(prefix="/splitbills", tags=["splitbills"])


@router.get("/{splitbill_id}", response_model=SplitBillReadSchema)
async def read_splitbill(
    splitbill_id: int, session: AsyncSession = Depends(get_session)
):
    splitbill = await get_splitbill_view(session, splitbill_id)
    if not splitbill:
        raise HTTPException(status_code=404, detail="Split bill not found")

    return SplitBillReadSchema.model_validate(splitbill)


@router.post("/")
async def create_splitbill(
    splitbill_data: SplitBillCreateSchema,
    session: AsyncSession = Depends(get_session),
):
    db_splitbill = SplitBillsOrm(
        title=splitbill_data.title,
        currency=splitbill_data.currency,
        owner_id=splitbill_data.owner_id,
        status=splitbill_data.status,
    )
    session.add(db_splitbill)
    await session.flush()

    result = await session.execute(
        select(UsersOrm).where(UsersOrm.id == db_splitbill.owner_id)
    )
    owner = result.scalar_one()

    owner_member = SplitBillMembersOrm(
        alias=owner.username,
        email=owner.email,
        splitbill_id=db_splitbill.id,
        user_id=db_splitbill.owner_id,
        invited_by=db_splitbill.owner_id,
    )
    session.add(owner_member)

    for member_data in splitbill_data.members:
        if member_data.email:
            result = await session.execute(
                select(UsersOrm).where(UsersOrm.email == member_data.email)
            )
            user = result.scalar_one_or_none()

            if user:
                member = SplitBillMembersOrm(
                    alias=member_data.alias,
                    email=user.email,
                    splitbill_id=db_splitbill.id,
                    user_id=user.id,
                    invited_by=splitbill_data.owner_id,
                )
            else:
                pending_user = PendingUsersOrm(
                    email=member_data.email, alias=member_data.alias
                )
                session.add(pending_user)
                await session.flush()

                member = SplitBillMembersOrm(
                    alias=member_data.alias,
                    email=member_data.email,
                    splitbill_id=db_splitbill.id,
                    pending_user_id=pending_user.id,
                    invited_by=splitbill_data.owner_id,
                )
        else:
            pending_user = PendingUsersOrm(alias=member_data.alias)
            session.add(pending_user)
            await session.flush()

            member = SplitBillMembersOrm(
                alias=member_data.alias,
                splitbill_id=db_splitbill.id,
                pending_user_id=pending_user.id,
                invited_by=splitbill_data.owner_id,
            )

        session.add(member)

    await session.commit()
    await session.refresh(db_splitbill)
    return db_splitbill


@router.get("/{splitbill_id}/expenses", response_model=List[ExpenseReadSchema])
async def read_expenses(
    splitbill_id: int, session: AsyncSession = Depends(get_session)
):
    # Eager-load assignments
    stmt = (
        select(ExpensesOrm)
        .where(ExpensesOrm.splitbill_id == splitbill_id)
        .options(selectinload(ExpensesOrm.assignments))
    )
    result = await session.execute(stmt)
    expenses_list = result.scalars().all()

    return [ExpenseReadSchema.model_validate(e) for e in expenses_list]


@router.post("/{splitbill_id}/expenses")
async def create_expense(
    splitbill_id: int,
    expense_data: ExpenseCreateSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="SplitBill not found")

    db_expense = ExpensesOrm(
        title=expense_data.title,
        amount=expense_data.amount,
        type=expense_data.type,
        paid_by_id=expense_data.paid_by_id,
        splitbill_id=splitbill_id,
        assignments=[],
    )
    session.add(db_expense)
    await session.flush()

    result = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id
        )
    )
    members = result.scalars().all()
    if not members:
        raise HTTPException(
            status_code=400, detail="No members found for this splitbill"
        )

    if expense_data.type == ExpenseTypeEnum.equal:
        share_per_member = db_expense.amount / len(members)
        for member in members:
            assignment = ExpenseAssignmentOrm(
                expense_id=db_expense.id,
                member_id=member.id,
                share_amount=share_per_member,
            )
            session.add(assignment)

    elif expense_data.type == ExpenseTypeEnum.percentage:
        if not expense_data.assignments:
            raise HTTPException(
                status_code=400,
                detail="Assignments required for percentage expense",
            )

        total_percentage = sum(a.share_amount for a in expense_data.assignments)
        if total_percentage != 100:
            raise HTTPException(
                status_code=400,
                detail=f"Total percentage must equal 100, got {total_percentage}",
            )

        for a in expense_data.assignments:
            share_amount = (
                db_expense.amount * (a.share_amount / Decimal("100"))
            ).quantize(Decimal("0.01"))

            assignment = ExpenseAssignmentOrm(
                expense_id=db_expense.id,
                member_id=a.member_id,
                share_amount=share_amount,
            )
            session.add(assignment)

    elif expense_data.type == ExpenseTypeEnum.custom:
        if not expense_data.assignments:
            raise HTTPException(
                status_code=400,
                detail="Assignments required for custom expense",
            )

        total_amount = sum(
            a.share_amount for a in expense_data.assignments if a.share_amount
        )
        if total_amount != db_expense.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Sum of all shared amounts must equal {db_expense.amount}, but got {total_amount}",
            )

        for a in expense_data.assignments:
            assignment = ExpenseAssignmentOrm(
                expense_id=db_expense.id,
                member_id=a.member_id,
                share_amount=a.share_amount,
            )
            session.add(assignment)

    else:
        raise HTTPException(status_code=400, detail="Invalid expense type")

    await session.commit()
    await session.refresh(db_expense)
    return db_expense


@router.post("/{splitbill_id}/calculate-balances")
async def calculate_splitbill_balances(
    splitbill_id: int, session: AsyncSession = Depends(get_session)
):
    balances = await calculate_balances(splitbill_id, session)
    if balances is None:
        raise HTTPException(status_code=404, detail="Splitbill not found")
    return balances


@router.post("/{splitbill_id}/money-given", response_model=MoneyGivenReadSchema)
async def create_money_given(
    splitbill_id: int,
    transaction_data: MoneyGivenCreateSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="SplitBill not found")

    db_transaction = MoneyGivenOrm(
        title=transaction_data.title,
        amount=Decimal(transaction_data.amount).quantize(Decimal("0.01")),
        given_by=transaction_data.given_by,
        given_to=transaction_data.given_to,
        splitbill_id=splitbill_id,
    )
    session.add(db_transaction)
    await session.flush()

    await _apply_money_given_to_balances(
        session=session,
        splitbill_id=splitbill_id,
        giver_member_id=db_transaction.given_by,
        recipient_member_id=db_transaction.given_to,
        amount=db_transaction.amount,
    )

    await session.commit()
    await session.refresh(db_transaction)
    return MoneyGivenReadSchema.model_validate(db_transaction)


@router.post("/{splitbill_id}/comments", response_model=CommentReadSchema)
async def create_comment(
    splitbill_id: int,
    comment: CommentCreateSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = result.scalar_one_or_none()

    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    author_result = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id,
            SplitBillMembersOrm.user_id == comment.author_id,
        )
    )
    author = author_result.scalar_one_or_none()
    if not author:
        raise HTTPException(
            status_code=400,
            detail="Author must be a member of this splitbill",
        )
    db_comment = CommentsOrm(
        text=comment.text, author_id=comment.author_id, splitbill_id=splitbill_id
    )

    session.add(db_comment)
    await session.commit()
    await session.refresh(db_comment)

    return CommentReadSchema.model_validate(db_comment)
