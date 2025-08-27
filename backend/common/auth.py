# auth.py
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def validate_password(password: str) -> bool:
    import re
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$'
    return re.match(pattern, password) is not None

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def safe_verify_password(plain: str, hashed: str) -> bool:
    try:
        if not hashed or not hashed.startswith("$2"):
            return False
        return pwd_context.verify(plain, hashed)
    except UnknownHashError:
        return False
    except Exception:
        return False
