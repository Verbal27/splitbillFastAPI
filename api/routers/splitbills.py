from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.utils import (
    calculate_balances,
    ensure_active_splitbill,
    generate_guest_link,
    get_splitbill_view,
    send_add_email,
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
    StatusEnum,
    UsersOrm,
)
from ..schemas.splitbill_schema import (
    CommentCreateSchema,
    CommentReadSchema,
    ExpenseCreateSchema,
    ExpenseReadSchema,
    ExpenseUpdateSchema,
    MoneyGivenCreateSchema,
    MoneyGivenReadSchema,
    MoneyGivenUpdateSchema,
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


@router.post("/", response_model=SplitBillReadSchema)
async def create_splitbill(
    request: Request,
    splitbill_data: SplitBillCreateSchema,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    db_splitbill = SplitBillsOrm(
        title=splitbill_data.title,
        currency=splitbill_data.currency,
        owner_id=current_user.id,
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

    members_to_notify = []

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
        if member.email:
            members_to_notify.append(member.email)

    splitbill_view = await get_splitbill_view(session, db_splitbill.id)
    res = SplitBillReadSchema.model_validate(splitbill_view)

    link = await generate_guest_link(db_splitbill.id, request, session)

    for email in members_to_notify:
        await send_add_email(
            email,
            splitbill_title=splitbill_data.title,
            added_by=current_user.username,
            link=link,
        )
    print(f"Generated guest link: {link}")
    return res


@router.get("/{splitbill_id}", response_model=SplitBillReadSchema)
async def read_splitbill(
    splitbill_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    splitbill = await get_splitbill_view(session, splitbill_id)
    if not splitbill:
        raise HTTPException(status_code=404, detail="Split bill not found")
    user = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id,
            SplitBillMembersOrm.user_id == current_user.id,
        )
    )
    member = user.scalar_one_or_none()
    if not (member or splitbill.owner_id == current_user.id):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this splitbill"
        )

    return SplitBillReadSchema.model_validate(splitbill)


@router.get("/{splitbill_id}/expenses", response_model=List[ExpenseReadSchema])
async def read_expenses(
    splitbill_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
):
    user = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id,
            SplitBillMembersOrm.user_id == current_user.id,
        )
    )
    member = user.scalar_one_or_none()
    if not member:
        owner = await session.execute(
            select(SplitBillsOrm.owner_id).where(SplitBillsOrm.id == splitbill_id)
        )
        if owner.scalar_one_or_none() != current_user.id:
            raise HTTPException(
                status_code=403, detail="Not authorized to view expenses"
            )

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
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="SplitBill not found")

    member_check = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id,
            SplitBillMembersOrm.user_id == current_user.id,
        )
    )
    if not member_check.scalar_one_or_none() and splitbill.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to add expenses")

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

    await session.flush()
    await session.refresh(db_expense)
    await calculate_balances(splitbill.id, session)
    await session.commit()
    return db_expense


@router.patch("/{splitbill_id}/expenses/{exp_id}")
async def update_expense(
    splitbill_id: int,
    exp_id: int,
    new_data: ExpenseUpdateSchema,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    try:
        result = await session.execute(
            select(SplitBillsOrm)
            .where(SplitBillsOrm.id == splitbill_id)
            .options(
                selectinload(SplitBillsOrm.members),
                selectinload(SplitBillsOrm.expenses).selectinload(
                    ExpensesOrm.assignments
                ),
            )
        )
        db_splitbill = result.scalar_one_or_none()
        if not db_splitbill:
            raise HTTPException(status_code=404, detail="Splitbill not found")

        result = await session.execute(
            select(ExpensesOrm)
            .where(ExpensesOrm.id == exp_id)
            .options(selectinload(ExpensesOrm.assignments))
        )
        db_exp = result.scalar_one_or_none()
        if not db_exp:
            raise HTTPException(status_code=404, detail="Expense not found")

        if current_user.id != db_splitbill.owner_id:
            raise HTTPException(
                status_code=403, detail="Only owner can modify expenses"
            )

        if new_data.title is not None:
            db_exp.title = new_data.title
        if new_data.amount is not None:
            db_exp.amount = new_data.amount
        if new_data.type is not None:
            db_exp.type = new_data.type
        if new_data.paid_by_id is not None:
            member_ids = [m.id for m in db_splitbill.members]
            if new_data.paid_by_id not in member_ids:
                raise HTTPException(
                    status_code=400, detail="Paid by user must be a splitbill member"
                )
            db_exp.paid_by_id = new_data.paid_by_id

        await session.execute(
            delete(ExpenseAssignmentOrm).where(
                ExpenseAssignmentOrm.expense_id == db_exp.id
            )
        )

        members = db_splitbill.members
        if db_exp.type == ExpenseTypeEnum.equal:
            share_per_member = (Decimal(db_exp.amount) / len(members)).quantize(
                Decimal("0.01")
            )
            for member in members:
                session.add(
                    ExpenseAssignmentOrm(
                        expense_id=db_exp.id,
                        member_id=member.id,
                        share_amount=share_per_member,
                    )
                )

        elif db_exp.type == ExpenseTypeEnum.percentage:
            if not new_data.assignments:
                raise HTTPException(
                    status_code=400,
                    detail="Assignments required for percentage expense",
                )
            total_percentage = sum(
                Decimal(a.share_amount or 0) for a in new_data.assignments
            )
            if total_percentage != 100:
                raise HTTPException(
                    status_code=400,
                    detail=f"Percentages must total 100, got {total_percentage}",
                )
            for a in new_data.assignments:
                share_amount = (
                    Decimal(db_exp.amount) * (Decimal(a.share_amount) / 100)  # type: ignore
                ).quantize(Decimal("0.01"))
                session.add(
                    ExpenseAssignmentOrm(
                        expense_id=db_exp.id,
                        member_id=a.member_id,
                        share_amount=share_amount,
                    )
                )

        elif db_exp.type == ExpenseTypeEnum.custom:
            if not new_data.assignments:
                raise HTTPException(
                    status_code=400, detail="Assignments required for custom expense"
                )
            total_amount = sum(
                Decimal(a.share_amount or 0) for a in new_data.assignments
            )
            if total_amount != Decimal(db_exp.amount):
                raise HTTPException(
                    status_code=400,
                    detail=f"Assignments must total {db_exp.amount}, got {total_amount}",
                )
            for a in new_data.assignments:
                session.add(
                    ExpenseAssignmentOrm(
                        expense_id=db_exp.id,
                        member_id=a.member_id,
                        share_amount=Decimal(a.share_amount).quantize(Decimal("0.01")),  # type: ignore
                    )
                )

        await session.flush()
        await session.refresh(db_exp)

        await calculate_balances(db_splitbill.id, session)
        await session.commit()

        return db_exp

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{splitbill_id}/expenses/{exp_id}")
async def delete_expense(
    splitbill_id: int,
    exp_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    splitbill = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    db_splitbill = splitbill.scalar_one_or_none()
    if not db_splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    expense = await session.execute(select(ExpensesOrm).where(ExpensesOrm.id == exp_id))
    db_exp = expense.scalar_one_or_none()
    if not db_exp:
        raise HTTPException(status_code=404, detail="Expense not found")

    if db_splitbill.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only splitbill owner can delete expenses"
        )

    await session.delete(db_exp)
    await session.commit()
    await calculate_balances(db_splitbill.id, session)

    return {"status": 200, "detail": "Deleted successfully"}


@router.post("/{splitbill_id}/money-given")
async def create_money_given(
    splitbill_id: int,
    payload: MoneyGivenCreateSchema,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    member_check = await session.execute(
        select(SplitBillMembersOrm).where(
            SplitBillMembersOrm.splitbill_id == splitbill_id,
            SplitBillMembersOrm.user_id == current_user.id,
        )
    )
    member = member_check.scalar_one_or_none()
    owner_check = await session.execute(
        select(SplitBillsOrm.owner_id).where(SplitBillsOrm.id == splitbill_id)
    )
    owner_id = owner_check.scalar_one_or_none()

    if not (member or current_user.id == owner_id):
        raise HTTPException(
            status_code=403, detail="Not authorized to add transactions"
        )
    new_tx = MoneyGivenOrm(
        title=payload.title,
        amount=payload.amount,
        given_by=payload.given_by,
        given_to=payload.given_to,
        splitbill_id=splitbill_id,
    )
    session.add(new_tx)
    await session.flush()

    await calculate_balances(splitbill_id, session)

    await session.commit()
    await session.refresh(new_tx)
    return new_tx


@router.patch(
    "/{splitbill_id}/money-given/{mg_id}", response_model=MoneyGivenReadSchema
)
async def modify_transaction(
    splitbill_id: int,
    mg_id: int,
    new_data: MoneyGivenUpdateSchema,
    session: AsyncSession = Depends(get_session),
    current_user: UsersOrm = Depends(get_current_user),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    result = await session.execute(
        select(SplitBillsOrm)
        .where(SplitBillsOrm.id == splitbill_id)
        .options(selectinload(SplitBillsOrm.members))
    )

    db_splitbill = result.scalar_one_or_none()
    if not db_splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    result = await session.execute(
        select(MoneyGivenOrm).where(MoneyGivenOrm.id == mg_id)
    )
    db_mg = result.scalar_one_or_none()
    if not db_mg:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if db_splitbill.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only splitbill owner can modify transactions"
        )

    member_ids = [m.user_id for m in db_splitbill.members]

    if new_data.title is not None:
        db_mg.title = new_data.title
    if new_data.amount is not None:
        db_mg.amount = new_data.amount
    if new_data.given_by is not None:
        if new_data.given_by not in member_ids:
            raise HTTPException(
                status_code=400, detail="Given_by user must be a splitbill member"
            )
        db_mg.given_by = new_data.given_by
    if new_data.given_to is not None:
        if new_data.given_to not in member_ids:
            raise HTTPException(
                status_code=400, detail="Given_to user must be a splitbill member"
            )
        db_mg.given_to = new_data.given_to

    await session.commit()
    await session.refresh(db_mg)
    await calculate_balances(db_splitbill.id, session)
    return db_mg


@router.delete("/{splitbill_id}/money-given/{mg_id}")
async def delete_transaction(
    splitbill_id: int,
    mg_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    result = await session.execute(
        select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
    )
    db_splitbill = result.scalar_one_or_none()
    if not db_splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    result = await session.execute(
        select(MoneyGivenOrm).where(MoneyGivenOrm.id == mg_id)
    )
    db_mg = result.scalar_one_or_none()
    if not db_mg:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if db_splitbill.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only splitbill owner can delete transactions"
        )

    await session.delete(db_mg)
    await session.commit()
    await calculate_balances(db_splitbill.id, session)

    return {"status": 200, "detail": "Deleted successfully"}


@router.post("/{splitbill_id}/comments", response_model=CommentReadSchema)
async def create_comment(
    splitbill_id: int,
    comment: CommentCreateSchema,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    splitbill = (
        await session.execute(
            select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
        )
    ).scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    member = (
        await session.execute(
            select(SplitBillMembersOrm).where(
                SplitBillMembersOrm.splitbill_id == splitbill_id,
                SplitBillMembersOrm.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if not member and splitbill.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to comment on this splitbill"
        )

    db_comment = CommentsOrm(
        text=comment.text,
        author_id=member.id if member else None,
        splitbill_id=splitbill_id,
    )

    session.add(db_comment)
    await session.commit()
    await session.refresh(db_comment)

    return CommentReadSchema.model_validate(db_comment)


@router.post("/{splitbill_id}/add-members", response_model=SplitBillMemberReadSchema)
async def add_members(
    request: Request,
    member_data: SplitBillMemberCreateSchema,
    splitbill_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
):
    db_user = (
        await session.execute(select(UsersOrm).where(UsersOrm.id == current_user.id))
    ).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="No user found")

    splitbill = (
        await session.execute(
            select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
        )
    ).scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if db_user.id != splitbill.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can add members")

    existing_member = (
        await session.execute(
            select(SplitBillMembersOrm)
            .where(SplitBillMembersOrm.splitbill_id == splitbill.id)
            .where(SplitBillMembersOrm.email == member_data.email)
        )
    ).scalar_one_or_none()
    if existing_member:
        raise HTTPException(status_code=400, detail="Member already exists")

    invited_user = None
    if member_data.email:
        invited_user = (
            await session.execute(
                select(UsersOrm).where(UsersOrm.email == member_data.email)
            )
        ).scalar_one_or_none()

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

    if member.email:
        try:
            link = await generate_guest_link(splitbill.id, request, session)
            await send_add_email(
                member.email,
                splitbill_title=splitbill.title,
                added_by=current_user.username,
                link=link,
            )
            print(link)
        except Exception as e:
            raise HTTPException(status_code=500, detail=e)

    return SplitBillMemberReadSchema.model_validate(member, from_attributes=True)


@router.delete("/{splitbill_id}/remove-member")
async def remove_member(
    user_remove: SplitBillMemberRemoveSchema,
    splitbill_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    splitbill: SplitBillsOrm = Depends(ensure_active_splitbill),
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
    db_user = (
        await session.execute(select(UsersOrm).where(UsersOrm.id == current_user.id))
    ).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="No user found")

    splitbill = (
        await session.execute(
            select(SplitBillsOrm).where(SplitBillsOrm.id == splitbill_id)
        )
    ).scalar_one_or_none()
    if not splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if db_user.id != splitbill.owner_id:
        raise HTTPException(status_code=403, detail="Only owner can modify members")

    member = (
        await session.execute(
            select(SplitBillMembersOrm).where(SplitBillMembersOrm.id == member_data.id)
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member_data.alias is not None:
        member.alias = member_data.alias

    if member_data.email is not None and member_data.email != member.email:
        existing_member = (
            await session.execute(
                select(SplitBillMembersOrm)
                .where(SplitBillMembersOrm.splitbill_id == splitbill_id)
                .where(SplitBillMembersOrm.email == member_data.email)
                .where(SplitBillMembersOrm.id != member_data.id)
            )
        ).scalar_one_or_none()
        if existing_member:
            raise HTTPException(
                status_code=400, detail="Email already used for another member"
            )

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

    await session.commit()
    await session.refresh(member)

    if member_data.email:
        try:
            await send_add_email(
                member_data.email,
                splitbill_title=splitbill.title,
                added_by=current_user.username,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=e)

    return SplitBillMemberReadSchema.model_validate(member, from_attributes=True)


@router.patch("/{splitbill_id}/close-splitbill")
async def close_splitbill(
    splitbill_id: int,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SplitBillsOrm)
        .options(selectinload(SplitBillsOrm.balances))
        .where(SplitBillsOrm.id == splitbill_id)
    )
    db_splitbill = result.scalar_one_or_none()
    if not db_splitbill:
        raise HTTPException(status_code=404, detail="Splitbill not found")

    if current_user.id != db_splitbill.owner_id:
        raise HTTPException(
            status_code=403, detail="Only owner can mark splitbill as solved"
        )

    unsettled_balances = [
        b for b in db_splitbill.balances if b.status != StatusEnum.settled
    ]
    if unsettled_balances:
        raise HTTPException(
            status_code=400,
            detail="Cannot close splitbill until all balances are settled",
        )

    db_splitbill.status = StatusEnum.settled
    await session.commit()
    await session.refresh(db_splitbill)

    return {"message": "Splitbill closed successfully"}
