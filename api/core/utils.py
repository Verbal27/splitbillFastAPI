from datetime import datetime, timedelta, timezone
import os
import secrets
from fastapi import Depends, HTTPException, Request
from sendgrid import SendGridAPIClient, Mail
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from api.core.config import settings

from api.db.database import get_session
from api.models.models import (
    BalancesOrm,
    ExpensesOrm,
    GuestsOrm,
    SplitBillMembersOrm,
    SplitBillsOrm,
    StatusEnum,
)


async def ensure_active_splitbill(
    splitbill_id: int,
    session: AsyncSession = Depends(get_session),
):
    s = await session.execute(
        select(SplitBillsOrm).where(
            (SplitBillsOrm.id == splitbill_id)
            & (SplitBillsOrm.status == StatusEnum.active)
        )
    )
    db_s = s.scalar_one_or_none()
    if not db_s:
        raise HTTPException(status_code=403, detail="Cannot modify a settled splitbill")
    return db_s


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
            selectinload(SplitBillsOrm.balances),
        )
    )
    result = await session.execute(stmt)
    splitbill = result.scalar_one_or_none()
    if not splitbill:
        return None
    if splitbill.status == StatusEnum.settled:
        return

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

    active_balances = {
        b.id: b for b in splitbill.balances if b.status == StatusEnum.active
    }

    for bal_id, bal in active_balances.items():
        debtor = bal.from_member_id
        creditor = bal.to_member_id
        if debtor in cleaned_balances and creditor in cleaned_balances[debtor]:
            bal.amount = cleaned_balances[debtor][creditor].quantize(Decimal("0.01"))
            del cleaned_balances[debtor][creditor]
        else:
            bal.status = StatusEnum.settled
            bal.amount = bal.amount.quantize(Decimal("0.01"))

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


async def generate_guest_link(
    splitbill_id: int, request: Request, session: AsyncSession
):
    token = secrets.token_urlsafe(32)
    guest = GuestsOrm(
        token=token,
        splitbill_id=splitbill_id,
        expires=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    session.add(guest)
    await session.commit()
    base_url = str(request.base_url)
    link = f"{base_url}guest-access/{token}"

    return link


async def send_add_email(
    recipient: str, splitbill_title: str, added_by: str, link: str
):
    message = Mail(
        from_email=os.environ.get("MAIL_FROM"),
        to_emails=recipient,
        subject="Someone added you to SplitBill",
        html_content=f"You were added to SplitBill '{splitbill_title}' by {added_by}. If you don't have an account yet, you can view it here: {link}",
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(str(e))


async def send_activation_email(user_email: str, token: str):
    activation_link = f"{settings.url}/activate?token={token}"
    message = Mail(
        from_email=os.environ.get("MAIL_FROM"),
        to_emails=user_email,
        subject="Activate Your Account",
        html_content=f"Welcome! Please activate your account by clicking the link: {activation_link}",
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(str(e))


async def send_reset_token(user_email: str, token: str):
    reset_link = f"{settings.url}/reset-password-complete?token={token}"
    message = Mail(
        from_email=os.environ.get("MAIL_FROM"),
        to_emails=user_email,
        subject="Reset password",
        html_content=f"You requested to reset password. Do it following this link: {reset_link}",
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(str(e))
