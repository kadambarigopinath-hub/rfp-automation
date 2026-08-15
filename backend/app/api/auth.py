from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_password, create_session_token, SESSION_COOKIE_NAME
from app.models.models import User
from app.services.audit import log_action

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...),
                  db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.active == True).first()  # noqa: E712
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

    log_action(db, user.id, "login", "session", user.id)
    token = create_session_token(user.username)
    response = RedirectResponse(url="/kb", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, max_age=60 * 60 * 8)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
