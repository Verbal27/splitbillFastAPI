from decimal import Decimal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.models import (
    BalancesOrm,
    ExpensesOrm,
    SplitBillMembersOrm,
    SplitBillsOrm,
    StatusEnum,
)


async def get_splitbill_view(session: AsyncSession, splitbill_id: int):
    stmt = (
        select(SplitBillsOrm)
        .where(SplitBillsOrm.id == splitbill_id)
        .options(
            selectinload(SplitBillsOrm.members).selectinload(SplitBillMembersOrm.user),
            selectinload(SplitBillsOrm.members).selectinload(
                SplitBillMembersOrm.pending_user
            ),
            selectinload(SplitBillsOrm.expenses).selectinload(ExpensesOrm.assignments),
            selectinload(SplitBillsOrm.comments),
            selectinload(SplitBillsOrm.balances),
            selectinload(SplitBillsOrm.money_given),
            selectinload(SplitBillsOrm.owner),
        )
    )
    result = await session.execute(stmt)
    splitbill = result.scalar_one_or_none()
    return splitbill


async def calculate_balances(splitbill_id: int, session: AsyncSession):
    """Recalculate balances for a splitbill, preserving settled balances."""
    stmt = (
        select(SplitBillsOrm)
        .where(SplitBillsOrm.id == splitbill_id)
        .options(
            selectinload(SplitBillsOrm.members),
            selectinload(SplitBillsOrm.expenses).selectinload(ExpensesOrm.assignments),
            selectinload(SplitBillsOrm.money_given),
            selectinload(SplitBillsOrm.balances),
        )
    )
    result = await session.execute(stmt)
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        return None

    member_balances = {}
    for member in splitbill.members:
        net_paid = sum(
            exp.amount for exp in splitbill.expenses if exp.paid_by_id == member.id
        )
        net_share = sum(
            assign.share_amount
            for exp in splitbill.expenses
            for assign in exp.assignments
            if assign.member_id == member.id
        )
        money_out = sum(
            mg.amount for mg in splitbill.money_given if mg.given_by == member.id
        )
        money_in = sum(
            mg.amount for mg in splitbill.money_given if mg.given_to == member.id
        )

        balance = (
            Decimal(net_paid)
            - Decimal(net_share)
            + Decimal(money_in)
            - Decimal(money_out)
        ).quantize(Decimal("0.01"))
        member_balances[member.id] = balance

    creditors = [
        {"id": m_id, "balance": b} for m_id, b in member_balances.items() if b > 0
    ]
    debtors = [
        {"id": m_id, "balance": b} for m_id, b in member_balances.items() if b < 0
    ]

    await session.execute(
        delete(BalancesOrm).where(
            BalancesOrm.splitbill_id == splitbill_id,
            BalancesOrm.status == StatusEnum.active,
        )
    )

    for debtor in debtors:
        for creditor in creditors:
            if debtor["balance"] == 0:
                break
            amount = min(-debtor["balance"], creditor["balance"]).quantize(
                Decimal("0.01")
            )
            if amount == 0:
                continue

            new_balance = BalancesOrm(
                from_member_id=debtor["id"],
                to_member_id=creditor["id"],
                splitbill_id=splitbill_id,
                amount=amount,
                status=StatusEnum.active,
            )
            session.add(new_balance)

            debtor["balance"] += amount
            creditor["balance"] -= amount

    await session.commit()


async def _apply_money_given_to_balances(
    session: AsyncSession,
    splitbill_id: int,
    giver_member_id: int,
    recipient_member_id: int,
    amount: Decimal,
):
    """Apply a money-given transaction, adjusting balances correctly."""
    amount = Decimal(amount).quantize(Decimal("0.01"))

    # Step 1: Check if recipient owes giver (opposite balance)
    res = await session.execute(
        select(BalancesOrm).where(
            BalancesOrm.from_member_id == recipient_member_id,
            BalancesOrm.to_member_id == giver_member_id,
            BalancesOrm.splitbill_id == splitbill_id,
        )
    )
    opposite = res.scalar_one_or_none()

    if opposite:
        if amount < opposite.amount:
            opposite.amount = (opposite.amount - amount).quantize(Decimal("0.01"))
            if opposite.amount == 0:
                opposite.status = StatusEnum.settled
            return
        elif amount == opposite.amount:
            opposite.status = StatusEnum.settled
            return
        else:
            remaining = (amount - opposite.amount).quantize(Decimal("0.01"))
            await session.delete(opposite)
            amount = remaining  # continue with remaining amount as new debt

    # Step 2: Check if giver already owes recipient (direct balance)
    res = await session.execute(
        select(BalancesOrm).where(
            BalancesOrm.from_member_id == giver_member_id,
            BalancesOrm.to_member_id == recipient_member_id,
            BalancesOrm.splitbill_id == splitbill_id,
        )
    )
    direct = res.scalar_one_or_none()

    if direct:
        direct.amount = (direct.amount + amount).quantize(Decimal("0.01"))
        direct.status = StatusEnum.active
    else:
        # Step 3: No balance exists in either direction, create new balance
        new_bal = BalancesOrm(
            from_member_id=giver_member_id,
            to_member_id=recipient_member_id,
            splitbill_id=splitbill_id,
            amount=amount,
            status=StatusEnum.active,
        )
        session.add(new_bal)
