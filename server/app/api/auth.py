from datetime import timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SESSION_COOKIE, SESSION_SECONDS, enforce_auth_rate_limit, get_current_user
from app.config import get_settings
from app.core.security import hash_api_key, hash_password, verify_password
from app.db import get_db
from app.models import BrowserSession, User, utcnow
from app.schemas.auth import DeleteAccountRequest, LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    await db.flush()
    await start_session(request, response, db, user)
    return UserOut.model_validate(user)


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    # Verify against a constant dummy hash on unknown emails to keep timing uniform.
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await start_session(request, response, db, user)
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


async def start_session(request: Request, response: Response, db: AsyncSession, user: User) -> None:
    previous = request.cookies.get(SESSION_COOKIE)
    await db.execute(delete(BrowserSession).where(BrowserSession.expires_at <= utcnow()))
    if previous:
        await db.execute(
            delete(BrowserSession).where(BrowserSession.token_hash == hash_api_key(previous))
        )
    token = token_urlsafe(32)
    db.add(
        BrowserSession(
            token_hash=hash_api_key(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(seconds=SESSION_SECONDS),
        )
    )
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=get_settings().environment == "production",
        samesite="lax",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await db.execute(
            delete(BrowserSession).where(BrowserSession.token_hash == hash_api_key(token))
        )
        await db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=get_settings().environment == "production",
    )


@router.delete(
    "/me", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(enforce_auth_rate_limit)]
)
async def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password")
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=get_settings().environment == "production",
    )


_DUMMY_HASH = hash_password("timing-equalizer-dummy-password")
