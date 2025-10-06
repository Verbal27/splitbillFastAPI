from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from api.db.database import get_session
from api.models.models import GuestsOrm, SplitBillsOrm

router = APIRouter()


@router.get("/guest-access/{token}")
async def view_as_guest(token: str, session: AsyncSession = Depends(get_session)):
    # Fetch guest by token
    guest_result = await session.execute(
        select(GuestsOrm).where(GuestsOrm.token == token)
    )
    db_guest = guest_result.scalar_one_or_none()

    if not db_guest:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    if db_guest.expires and db_guest.expires < datetime.now(tz=timezone.utc):
        raise HTTPException(status_code=403, detail="Token expired")

    # Fetch splitbill with all related objects eagerly loaded
    split_result = await session.execute(
        select(SplitBillsOrm)
        .options(
            selectinload(SplitBillsOrm.owner),
            selectinload(SplitBillsOrm.members),
            selectinload(SplitBillsOrm.expenses),
            selectinload(SplitBillsOrm.money_given),
            selectinload(SplitBillsOrm.comments),
            selectinload(SplitBillsOrm.balances),  # eagerly load balances
        )
        .where(SplitBillsOrm.id == db_guest.splitbill_id)
    )
    db_splitbill = split_result.scalar_one_or_none()

    if not db_splitbill:
        raise HTTPException(
            status_code=404, detail="No splitbill found at this address"
        )

    # Build response
    response = {
        "title": db_splitbill.title,
        "date_created": db_splitbill.date_created.isoformat(),
        "owner": db_splitbill.owner.username if db_splitbill.owner else None,
        "members": [{"alias": m.alias, "email": m.email} for m in db_splitbill.members],
        "expenses": [
            {"title": e.title, "amount": e.amount, "type": e.type}
            for e in db_splitbill.expenses
        ],
        "transaction": [
            {
                "title": t.title,
                "amount": t.amount,
                "given_by": t.given_by,
                "given_to": t.given_to,
            }
            for t in db_splitbill.money_given
        ],
        "comments": [
            {"text": c.text, "author_id": c.author_id} for c in db_splitbill.comments
        ],
        "balances": [
            {
                "id": b.id,
                "amount": b.amount,
                "from_member_id": b.from_member_id,
                "to_member_id": b.to_member_id,
                "status": b.status,
            }
            for b in db_splitbill.balances
        ],
        "status": db_splitbill.status,
    }

    return response
