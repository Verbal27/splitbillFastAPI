import secrets
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, hash_password

from ..db.database import get_session
from ..models.models import (
    PasswordResetOrm,
    SplitBillMembersOrm,
    UserStatusEnum,
    UsersOrm,
    PendingUsersOrm,
)
from ..schemas.users_schema import (
    UserCreateSchema,
    UserPasswordUpdateSchema,
    UserReadSchema,
    UserUpdateSchema,
)


router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserReadSchema)
async def create_user(
    user: UserCreateSchema, session: AsyncSession = Depends(get_session)
):
    hashed_pw = hash_password(user.password)
    db_user = UsersOrm(
        username=user.username, email=user.email, hashed_password=hashed_pw
    )
    token = secrets.token_urlsafe(32)
    db_user.activation_token = token
    print(f"127.0.0.1:8000/docs/users/activate/{token}")
    session.add(db_user)
    try:
        await session.flush()
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

    pending_users_result = await session.execute(
        select(PendingUsersOrm).where(PendingUsersOrm.email == db_user.email)
    )
    pending_users = pending_users_result.scalars().all()

    for pending_user in pending_users:
        await session.delete(pending_user)

    await session.flush()

    user_dict = {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "status": db_user.status,
        "date_joined": db_user.date_joined,
        "date_updated": db_user.date_updated,
    }
    res = UserReadSchema.model_validate(user_dict)
    await session.commit()
    return res


@router.post("/reset-password")
async def reset_request(email: EmailStr, session: AsyncSession = Depends(get_session)):
    db_user = await session.execute(select(UsersOrm).where(UsersOrm.email == email))
    user = db_user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User with that email not found")

    generated_token = secrets.token_urlsafe()
    reset = PasswordResetOrm(token=generated_token, user_id=user.id)

    session.add(reset)
    await session.commit()
    await session.refresh(reset)

    return {"status": 200, "detail": "Token generated successfully"}


@router.post("/reset-password-complete")
async def reset_complete(
    token: str,
    user_update: UserPasswordUpdateSchema = Body(...),
    session: AsyncSession = Depends(get_session),
):
    user_token = await session.execute(
        select(PasswordResetOrm).where(PasswordResetOrm.token == token)
    )
    request = user_token.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="No request found for this token")

    update_data = user_update.model_dump(exclude_unset=True)
    update_data["hashed_password"] = hash_password(update_data.pop("password"))

    await session.execute(
        update(UsersOrm).where(UsersOrm.id == request.user_id).values(**update_data)
    )

    await session.delete(request)
    await session.commit()

    return {"status": 200, "detail": "Password reset successfully"}


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


@router.patch("/me/update")
async def update_user(
    user_update: UserUpdateSchema = Body(...),
    current_user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    update_data = user_update.model_dump(exclude_unset=True)

    password_changed = False
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
        password_changed = True

    await session.execute(
        update(UsersOrm).where(UsersOrm.id == current_user.id).values(**update_data)
    )
    await session.commit()

    if password_changed:
        return {"message": "Password has been updated successfully"}
    else:
        return {"message": "User profile updated successfully"}


@router.get("/activate")
async def activate_user(token: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(UsersOrm).where(UsersOrm.activation_token == token)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")

    user.status = UserStatusEnum.active
    user.activation_token = None
    session.add(user)
    await session.commit()
    return {"message": "User activated successfully"}


@router.delete("/delete")
async def delete_account(
    user: UsersOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await session.delete(user)
    await session.commit()

    return {"status": 200, "detail": "Account deleted successfully"}
