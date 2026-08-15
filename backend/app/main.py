from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api import auth, kb, admin

app = FastAPI(title="RFP Automation Platform - Knowledge Base Module")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return RedirectResponse(url="/login")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"status": "ok", "db_result": result}
