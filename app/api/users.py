from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_user_or_404
from app.db import get_session
from app.models.schemas import UserDetailOut, UserSummaryOut
from app.models.tables import User
from app.services.views import build_user_detail, build_user_summary

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserSummaryOut])
def list_users(session: Session = Depends(get_session)) -> list[UserSummaryOut]:
    users = session.query(User).order_by(User.external_id).all()
    return [build_user_summary(session, user) for user in users]


@router.get("/users/{user_id}", response_model=UserDetailOut)
def get_user(user_id: str, session: Session = Depends(get_session)) -> UserDetailOut:
    user = get_user_or_404(session, user_id)
    return build_user_detail(session, user)
