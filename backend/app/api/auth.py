from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.rate_limit import limiter
from app.core.config import get_settings
from app.core.security import create_token, decode_token, verify_password
from app.database.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, user.role, "access"),
        refresh_token=create_token(user.id, user.role, "refresh"),
    )


@router.post("/login", response_model=TokenPair)
@limiter.limit(get_settings().login_rate_limit)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == body.email.strip()))
    if not verify_password(body.password, user.password_hash if user else None) or not (
        user and user.is_active
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return _tokens(user)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(get_settings().login_rate_limit)
def refresh(request: Request, body: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _tokens(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
