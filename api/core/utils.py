from decimal import Decimal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.models import (
    BalancesOrm,
    ExpenseTypeEnum,
    ExpensesOrm,
    SplitBillMembersOrm,
    SplitBillsOrm,
    ExpenseAssignmentOrm,
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
    stmt = (
        select(SplitBillsOrm)
        .where(SplitBillsOrm.id == splitbill_id)
        .options(
            selectinload(SplitBillsOrm.members),
            selectinload(SplitBillsOrm.expenses).selectinload(ExpensesOrm.assignments),
            selectinload(SplitBillsOrm.money_given),
        )
    )
    result = await session.execute(stmt)
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        return None
    for exp in splitbill.expenses:
        if not exp.assignments or len(exp.assignments) == 0:
            members_ids = [m.id for m in splitbill.members]
            if exp.type == ExpenseTypeEnum.equal:
                share = (exp.amount / len(members_ids)).quantize(Decimal("0.01"))
                exp.assignments = [
                    ExpenseAssignmentOrm(member_id=m_id, share_amount=share)
                    for m_id in members_ids
                ]
            elif exp.type == ExpenseTypeEnum.percentage:
                share = (exp.amount / len(members_ids)).quantize(Decimal("0.01"))
                exp.assignments = [
                    ExpenseAssignmentOrm(member_id=m_id, share_amount=share)
                    for m_id in members_ids
                ]
            elif exp.type == ExpenseTypeEnum.custom:
                raise ValueError(
                    f"Expense {exp.id} of type 'custom' requires assignments"
                )

    member_balances = {}

    for member in splitbill.members:
        net_paid = sum(
            exp.amount for exp in splitbill.expenses if exp.paid_by_id == member.id
        )

        net_share = Decimal(0)
        for exp in splitbill.expenses:
            for assign in exp.assignments:
                if assign.member_id == member.id:
                    net_share += assign.share_amount

        money_out = sum(
            mg.amount for mg in splitbill.money_given if mg.given_by == member.id
        )
        money_in = sum(
            mg.amount for mg in splitbill.money_given if mg.given_to == member.id
        )

        member_balances[member.id] = net_paid - net_share + money_in - money_out

    creditors = []
    debtors = []

    for member_id, balance in member_balances.items():
        if balance > 0:
            creditors.append({"id": member_id, "balance": balance})
        elif balance < 0:
            debtors.append({"id": member_id, "balance": balance})

    balances_to_create = []

    for debtor in debtors:
        for creditor in creditors:
            if debtor["balance"] == 0:
                break
            amount = min(-debtor["balance"], creditor["balance"])
            balances_to_create.append(
                {
                    "from_member_id": debtor["id"],
                    "to_member_id": creditor["id"],
                    "amount": amount,
                }
            )
            debtor["balance"] += amount
            creditor["balance"] -= amount

        # Delete old balances
    await session.execute(
        delete(BalancesOrm).where(BalancesOrm.splitbill_id == splitbill_id)
    )

    # Add new balances
    for bal in balances_to_create:
        db_balance = BalancesOrm(
            from_member_id=bal["from_member_id"],
            to_member_id=bal["to_member_id"],
            splitbill_id=splitbill_id,
            amount=bal["amount"],
            status="active",
        )
        session.add(db_balance)

    await session.commit()
    return balances_to_create


async def _apply_money_given_to_balances(
    session: AsyncSession,
    splitbill_id: int,
    giver_member_id: int,
    recipient_member_id: int,
    amount: Decimal,
):
    amount = Decimal(amount).quantize(Decimal("0.01"))

    res = await session.execute(
        select(BalancesOrm).where(
            BalancesOrm.from_member_id == recipient_member_id,
            BalancesOrm.to_member_id == giver_member_id,
            BalancesOrm.splitbill_id == splitbill_id,
        )
    )
    direct = res.scalar_one_or_none()
    if direct:
        direct.amount = (direct.amount + amount).quantize(Decimal("0.01"))
        direct.status = StatusEnum.active
        return

    res = await session.execute(
        select(BalancesOrm).where(
            BalancesOrm.from_member_id == giver_member_id,
            BalancesOrm.to_member_id == recipient_member_id,
            BalancesOrm.splitbill_id == splitbill_id,
        )
    )
    opposite = res.scalar_one_or_none()
    if opposite:
        if opposite.amount > amount:
            opposite.amount = (opposite.amount - amount).quantize(Decimal("0.01"))
            return
        elif opposite.amount == amount:
            await session.delete(opposite)
            return
        else:
            net = (amount - opposite.amount).quantize(Decimal("0.01"))
            await session.delete(opposite)
            new_bal = BalancesOrm(
                from_member_id=recipient_member_id,
                to_member_id=giver_member_id,
                splitbill_id=splitbill_id,
                amount=net,
            )
            new_bal.status = StatusEnum.active
            session.add(new_bal)
            return

    new_bal = BalancesOrm(
        from_member_id=recipient_member_id,
        to_member_id=giver_member_id,
        splitbill_id=splitbill_id,
        amount=amount,
    )
    new_bal.status = StatusEnum.active
    session.add(new_bal)
    return
