from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, hash_password

from ..db.database import get_session
from ..models.models import SplitBillMembersOrm, UsersOrm, PendingUsersOrm
from ..schemas.users_schema import UserCreateSchema, UserReadSchema, UserUpdateSchema


router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserReadSchema)
async def create_user(
    user: UserCreateSchema, session: AsyncSession = Depends(get_session)
):
    hashed_pw = hash_password(user.password)
    db_user = UsersOrm(
        username=user.username, email=user.email, hashed_password=hashed_pw
    )
    session.add(db_user)
    try:
        await session.commit()
        await session.refresh(db_user)
    except Exception as e:
        await session.rollback()
        print(e)
        raise HTTPException(status_code=400, detail="Username or email already exists")

    pending_members_result = await session.execute(
        select(SplitBillMembersOrm).where(SplitBillMembersOrm.email == db_user.email)
    )
    pending_members = pending_members_result.scalars().all()
    for member in pending_members:
        member.user_id = db_user.id
        member.pending_user_id = None
        session.add(member)

    pending_user_record = await session.get(PendingUsersOrm, db_user.id)
    print(pending_user_record)
    if pending_user_record:
        await session.delete(pending_user_record)

    await session.commit()
    user_dict = {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "status": db_user.status,
        "date_joined": db_user.date_joined,
        "date_updated": db_user.date_updated,
    }
    print(user_dict)
    return UserReadSchema.model_validate(user_dict)


@router.get("/me", response_model=UserReadSchema)
async def get_user(
    user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(UsersOrm).where(UsersOrm.id == int(user.id)))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserReadSchema.model_validate(db_user)


@router.patch("/me/update", response_model=UserReadSchema)
async def update_user(
    user_update: UserUpdateSchema,
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        update(UsersOrm)
        .where(UsersOrm.id == current_user.id)
        .values(**user_update.model_dump(exclude_unset=True))
    )
    await session.commit()

    result = await session.execute(
        select(UsersOrm).where(UsersOrm.id == current_user.id)
    )
    updated_user = result.scalar_one_or_none()
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserReadSchema.model_validate(updated_user)
