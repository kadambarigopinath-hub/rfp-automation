from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.session_secret)

SESSION_COOKIE_NAME = "rfp_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8  # 8 hours


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session_token(username: str) -> str:
    return serializer.dumps({"username": username})


def read_session_token(token: str) -> str | None:
    """Returns the username if the token is valid and not expired, else None."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None
