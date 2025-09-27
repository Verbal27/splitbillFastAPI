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
from api.core.auth import get_current_user


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
    SplitBillMemberCreateSchema,
    SplitBillMemberReadSchema,
    SplitBillMemberRemoveSchema,
    SplitBillMemberUpdateSchema,
    SplitBillReadSchema,
)


router = APIRouter(prefix="/splitbills", tags=["splitbills"])


@router.get("/", response_model=list[SplitBillReadSchema])
async def list_all(
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    stmt = (
        select(SplitBillsOrm)
        .where(
            (SplitBillsOrm.owner_id == current_user.id)
            | (
                SplitBillsOrm.members.any(
                    SplitBillMembersOrm.user_id == current_user.id
                )
            )
        )
        .options(
            selectinload(SplitBillsOrm.members).selectinload(SplitBillMembersOrm.user),
            selectinload(SplitBillsOrm.members).selectinload(
                SplitBillMembersOrm.pending_user
            ),
            selectinload(SplitBillsOrm.expenses).selectinload(ExpensesOrm.assignments),
            selectinload(SplitBillsOrm.money_given),
            selectinload(SplitBillsOrm.comments),
            selectinload(SplitBillsOrm.balances),
            selectinload(SplitBillsOrm.owner),
        )
    )

    result = await session.execute(stmt)
    splitbills_list = result.scalars().all()

    if not splitbills_list:
        raise HTTPException(status_code=404, detail="No splitbills found")

    return [
        SplitBillReadSchema.model_validate(sb, from_attributes=True)
        for sb in splitbills_list
    ]


@router.get("/{splitbill_id}", response_model=SplitBillReadSchema)
async def read_splitbill(
    splitbill_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    splitbill = await get_splitbill_view(session, splitbill_id)
    if not splitbill:
        raise HTTPException(status_code=404, detail="Split bill not found")

    return SplitBillReadSchema.model_validate(splitbill)


@router.post("/", response_model=SplitBillReadSchema)
async def create_splitbill(
    splitbill_data: SplitBillCreateSchema,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    db_splitbill = SplitBillsOrm(
        title=splitbill_data.title,
        currency=splitbill_data.currency,
        owner_id=current_user.id,
        status=splitbill_data.status,
    )
    session.add(db_splitbill)
    await session.flush()

    owner_member = SplitBillMembersOrm(
        alias=current_user.username,
        email=current_user.email,
        splitbill_id=db_splitbill.id,
        user_id=current_user.id,
        invited_by=current_user.id,
    )
    session.add(owner_member)

    for member_data in splitbill_data.members:
        user = None
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
                invited_by=current_user.id,
            )
        else:
            pending_user = PendingUsersOrm(
                email=member_data.email,
                alias=member_data.alias,
            )
            session.add(pending_user)
            await session.flush()

            member = SplitBillMembersOrm(
                alias=member_data.alias,
                email=member_data.email,
                splitbill_id=db_splitbill.id,
                pending_user_id=pending_user.id,
                invited_by=current_user.id,
            )

        session.add(member)

    splitbill_view = await get_splitbill_view(session, db_splitbill.id)
    res = SplitBillReadSchema.model_validate(splitbill_view)
    await session.commit()
    return res


@router.get("/{splitbill_id}/expenses", response_model=List[ExpenseReadSchema])
async def read_expenses(
    splitbill_id: int, session: AsyncSession = Depends(get_session)
):
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

        total_percentage = sum(
            Decimal(a.share_amount)
            for a in expense_data.assignments
            if a.share_amount is not None
        )
        if total_percentage != 100:
            raise HTTPException(
                status_code=400,
                detail=f"Total percentage must equal 100, got {total_percentage}",
            )

        for a in expense_data.assignments:
            share_amount = (
                db_expense.amount * (a.share_amount / Decimal("100"))  # type: ignore
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
            Decimal(a.share_amount)
            for a in expense_data.assignments
            if a.share_amount is not None
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


@router.post("/{splitbill_id}/add-members", response_model=SplitBillMemberReadSchema)
async def add_members(
    member_data: SplitBillMemberCreateSchema,
    splitbill_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_result = await session.execute(
        select(UsersOrm).where(UsersOrm.id == current_user.id)
    )
    db_user = user_result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="No user found")

    splitbill_result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = splitbill_result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if db_user.id != splitbill.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can add members")

    invited_user = None
    if member_data.email:
        result = await session.execute(
            select(UsersOrm).where(UsersOrm.email == member_data.email)
        )
        invited_user = result.scalar_one_or_none()

    if invited_user:
        member = SplitBillMembersOrm(
            alias=member_data.alias,
            email=invited_user.email,
            splitbill_id=splitbill.id,
            user_id=invited_user.id,
            invited_by=current_user.id,
        )
    else:
        pending_user = PendingUsersOrm(
            email=member_data.email,
            alias=member_data.alias,
        )
        session.add(pending_user)
        await session.flush()

        member = SplitBillMembersOrm(
            alias=member_data.alias,
            email=member_data.email,
            splitbill_id=splitbill.id,
            pending_user_id=pending_user.id,
            invited_by=current_user.id,
        )

    session.add(member)
    await session.commit()
    await session.refresh(member)
    return SplitBillMemberReadSchema.model_validate(member, from_attributes=True)


@router.delete("/{splitbill_id}/remove-member")
async def remove_member(
    user_remove: SplitBillMemberRemoveSchema,
    splitbill_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_result = await session.execute(
        select(UsersOrm).where(UsersOrm.id == current_user.id)
    )
    db_user = user_result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="No user found")

    splitbill_result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = splitbill_result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if db_user.id != splitbill.owner_id:
        raise HTTPException(status_code=403, detail="Only the owner can remove members")

    member_result = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.id == user_remove.id,
            SplitBillMembersOrm.splitbill_id == splitbill_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this splitbill"
        )

    if member.user_id == splitbill.owner_id:
        raise HTTPException(
            status_code=400, detail="Cannot remove the owner from the splitbill"
        )

    await session.delete(member)
    await session.commit()

    return {"detail": f"Member {member.alias or member.email} removed successfully"}


@router.patch("/{splitbill_id}/modify-member", response_model=SplitBillMemberReadSchema)
async def modify_member(
    splitbill_id: int,
    member_data: SplitBillMemberUpdateSchema,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    user_result = await session.execute(
        select(UsersOrm).where(UsersOrm.id == current_user.id)
    )
    db_user = user_result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="No user found")

    splitbill_result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = splitbill_result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if db_user.id != splitbill.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can modify members")

    member_result = await session.execute(
        select(SplitBillMembersOrm).where(SplitBillMembersOrm.id == member_data.id)
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member_data.alias is not None:
        member.alias = member_data.alias
    if member_data.email is not None:
        member.email = member_data.email

    if member_data.email is not None:
        result = await session.execute(
            select(UsersOrm).where(UsersOrm.email == member_data.email)
        )
        new_user = result.scalar_one_or_none()

        member.email = member_data.email

        if new_user:
            member.user_id = new_user.id
            member.pending_user_id = None
        else:
            pending_user = PendingUsersOrm(email=member_data.email, alias=member.alias)
            session.add(pending_user)
            await session.flush()
            member.pending_user_id = pending_user.id
            member.user_id = None

    session.add(member)
    await session.flush()
    await session.refresh(member)
    await session.commit()
    return SplitBillMemberReadSchema.model_validate(member, from_attributes=True)
