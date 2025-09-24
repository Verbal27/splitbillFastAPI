from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from ..db.database import get_session
from ..models.models import UsersOrm
from ..schemas.users_schema import UserCreateSchema, UserReadSchema, UserUpdateSchema


router = APIRouter(prefix="/users", tags=["users"])


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


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

    return db_user


@router.get("/me", response_model=UserReadSchema)
async def get_user(id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(UsersOrm).where(UsersOrm.id == id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/me/update", response_model=UserUpdateSchema)
async def update_user(
    id: int, user: UserUpdateSchema, session: AsyncSession = Depends(get_session)
):
    await session.execute(
        update(UsersOrm)
        .where(UsersOrm.id == id)
        .values(**user.model_dump(exclude_unset=True))
    )
    await session.commit()

    result = await session.execute(select(UsersOrm).where(UsersOrm.id == id))
    updated_user = result.scalar_one_or_none()
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user
