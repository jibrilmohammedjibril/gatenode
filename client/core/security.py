import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from jose import jwt
from core.config import settings

# Password Hashing
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Ensure bytes
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# JWT
def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None, token_id: str = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    if token_id:
        to_encode["tid"] = token_id # 'tid' -> Token ID
        
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None, token_id: str = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "refresh": True}
    if token_id:
        to_encode["tid"] = token_id

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def verify_transaction_pin(user, pin: str) -> None:
    """
    Verify a 4-digit transaction PIN against the user's stored hash.
    Raises HTTPException on failure so routes don't need extra boilerplate.

    Usage in payment routes:
        from core.security import verify_transaction_pin
        verify_transaction_pin(current_user, data.transaction_pin)
    """
    from fastapi import HTTPException

    if not user.transaction_pin_hash:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "pin_not_set",
                "message": "You must set a Transaction PIN before making payments. Go to Settings → Security → Set PIN.",
            },
        )
    if not verify_password(pin, user.transaction_pin_hash):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "invalid_pin",
                "message": "Incorrect Transaction PIN. Please try again.",
            },
        )
