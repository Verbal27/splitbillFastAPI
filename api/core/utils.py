from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi_mail import FastMail, MessageSchema
from api.core.config import settings

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
    # Load splitbill with members, expenses, assignments, and money_given
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

    # Build member balances
    member_balances = {m.id: {} for m in splitbill.members}

    for exp in splitbill.expenses:
        payer_id = exp.paid_by_id
        for assign in exp.assignments:
            debtor_id = assign.member_id
            if debtor_id == payer_id:
                continue
            member_balances[debtor_id].setdefault(payer_id, Decimal("0.00"))
            member_balances[debtor_id][payer_id] += Decimal(assign.share_amount)

    for mg in splitbill.money_given:
        giver_id = mg.given_by
        receiver_id = mg.given_to
        if giver_id == receiver_id:
            continue
        member_balances[receiver_id].setdefault(giver_id, Decimal("0.00"))
        member_balances[receiver_id][giver_id] += Decimal(mg.amount)

    # Netting balances
    cleaned_balances = {}
    for debtor, creditors in member_balances.items():
        for creditor, amount in list(creditors.items()):
            if creditor in member_balances and debtor in member_balances[creditor]:
                net = amount - member_balances[creditor][debtor]
                if net > 0:
                    cleaned_balances.setdefault(debtor, {})[creditor] = net
                elif net < 0:
                    cleaned_balances.setdefault(creditor, {})[debtor] = -net
                member_balances[creditor].pop(debtor, None)
            else:
                cleaned_balances.setdefault(debtor, {})[creditor] = amount

    # Update old balances to 'settled' instead of deleting
    await session.execute(
        update(BalancesOrm)
        .where(
            BalancesOrm.splitbill_id == splitbill_id,
            BalancesOrm.status == StatusEnum.active,
        )
        .values(status=StatusEnum.settled, amount=Decimal("0.00"))
    )

    # Add new balances
    for debtor, creditors in cleaned_balances.items():
        for creditor, amount in creditors.items():
            if amount <= 0:
                continue
            session.add(
                BalancesOrm(
                    splitbill_id=splitbill_id,
                    from_member_id=debtor,
                    to_member_id=creditor,
                    amount=amount.quantize(Decimal("0.01")),
                    status=StatusEnum.active,
                )
            )

    await session.commit()


fm = FastMail(settings.mail_conf)


async def send_add_email(recipient: str, splitbill_title: str, added_by: str):
    message = MessageSchema(
        subject="Someone added you to SplitBill",
        recipients=[recipient],
        body=f"You were added to SplitBill '{splitbill_title}' by {added_by}.",
        subtype="plain",  # type: ignore
    )
    await fm.send_message(message)


async def send_activation_email(user_email: str, token: str):
    activation_link = f"{settings.url}/activate?token={token}"
    message = MessageSchema(
        subject="Activate Your Account",
        recipients=[user_email],
        body=f"Welcome! Please activate your account by clicking the link: {activation_link}",
        subtype="plain",
    )
    await fm.send_message(message)


async def send_reset_token(user_email: str, token: str):
    reset_link = f"{settings.url}/reset-password-complete?token={token}"
    message = MessageSchema(
        subject="Reset password",
        recipients=[user_email],
        body=f"You requested to reset password. Do it following this link: {reset_link}",
        subtype="plain",
    )
    await fm.send_message(message)
