from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import SESSION_COOKIE_NAME, read_session_token
from app.models.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    username = read_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired")
    user = db.query(User).filter(User.username == username, User.active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(user: User, allowed_roles: list) -> bool:
    return user.role.name in allowed_roles or user.role.name == "superadmin"
