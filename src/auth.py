"""认证模块 - 用户注册、登录、JWT 验证"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .database import User, get_engine

# bcrypt 加密轮数，可通过环境变量 BCRYPT_ROUNDS 覆盖（默认 12）
_BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    """密码 bcrypt 加密，rounds 可配置以随硬件升级调整安全强度"""
    rounds = min(max(_BCRYPT_ROUNDS, 10), 14)  # 限制在 10-14 之间，避免过慢或过弱
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def register(
    username: str,
    password: str,
    email: str | None = None,
    db_url: str | None = None,
) -> User:
    """
    用户注册
    
    Raises:
        ValueError: 用户名已存在
    """
    engine = get_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SessionLocal() as db:
        existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing:
            raise ValueError("用户名已存在")
        user = User(
            username=username,
            password_hash=hash_password(password),
            email=email or "",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def authenticate(username: str, password: str, db_url: str | None = None) -> tuple[User | None, str | None]:
    """
    验证用户名密码
    
    Returns:
        (User, None) - 认证成功
        (None, "user_not_found") - 用户不存在
        (None, "wrong_password") - 密码错误
    """
    engine = get_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            return None, "user_not_found"
        if not verify_password(password, user.password_hash):
            return None, "wrong_password"
        return user, None


def create_access_token(
    data: dict,
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
) -> str:
    """生成 JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=1440)  # 24h
    to_encode["exp"] = expire
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def verify_token(token: str, secret_key: str, algorithm: str = "HS256") -> dict | None:
    """
    验证 JWT token，返回 payload 或 None
    payload 包含: sub (user_id), username, exp
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except JWTError:
        return None


def get_user_by_id(user_id: int, db_url: str | None = None) -> User | None:
    """根据 ID 获取用户"""
    engine = get_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SessionLocal() as db:
        return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
