"""API 密钥管理模块 - 百炼 Dashscope 密钥的 CRUD 与验证"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .crypto_utils import decrypt_api_key, encrypt_api_key
from .database import APIKey, User, get_engine


def _get_session(db_url: str | None = None):
    engine = get_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def save_api_key(user_id: int, api_key: str, db_url: str | None = None) -> APIKey:
    """
    保存用户的百炼 API 密钥。
    每个用户只保留一条记录，存在则更新。
    若配置了 API_KEY_ENCRYPTION_KEY，则加密后存储；否则明文存储（向后兼容）。
    """
    plain = api_key.strip()
    encrypted = encrypt_api_key(plain)
    to_store = encrypted if encrypted else plain
    db = _get_session(db_url)
    try:
        existing = db.execute(select(APIKey).where(APIKey.user_id == user_id)).scalar_one_or_none()
        if existing:
            existing.api_key_encrypted = to_store
            db.commit()
            db.refresh(existing)
            return existing
        key_record = APIKey(user_id=user_id, api_key_encrypted=to_store)
        db.add(key_record)
        db.commit()
        db.refresh(key_record)
        return key_record
    finally:
        db.close()


def get_api_key(user_id: int, db_url: str | None = None) -> str | None:
    """获取用户的 API 密钥（明文）。若存储为加密格式则自动解密。"""
    db = _get_session(db_url)
    try:
        record = db.execute(select(APIKey).where(APIKey.user_id == user_id)).scalar_one_or_none()
        if not record:
            return None
        stored = record.api_key_encrypted
        decrypted = decrypt_api_key(stored)
        return decrypted if decrypted is not None else stored
    finally:
        db.close()


def get_api_key_masked(user_id: int, db_url: str | None = None) -> str | None:
    """获取脱敏显示的 API 密钥，如 sk-****...****abcd"""
    key = get_api_key(user_id, db_url)
    if not key or len(key) < 8:
        return None
    if key.startswith("sk-"):
        return f"sk-****...****{key[-4:]}"
    return f"****...****{key[-4:]}"


def update_api_key(user_id: int, api_key: str, db_url: str | None = None) -> APIKey:
    """更新 API 密钥"""
    return save_api_key(user_id, api_key, db_url)


def delete_api_key(user_id: int, db_url: str | None = None) -> bool:
    """删除用户的 API 密钥"""
    db = _get_session(db_url)
    try:
        record = db.execute(select(APIKey).where(APIKey.user_id == user_id)).scalar_one_or_none()
        if record:
            db.delete(record)
            db.commit()
            return True
        return False
    finally:
        db.close()


def update_last_used(user_id: int, db_url: str | None = None) -> None:
    """更新最后使用时间"""
    db = _get_session(db_url)
    try:
        record = db.execute(select(APIKey).where(APIKey.user_id == user_id)).scalar_one_or_none()
        if record:
            record.last_used = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def verify_api_key(api_key: str) -> tuple[bool, str]:
    """
    验证百炼 API 密钥是否有效。
    通过调用 Dashscope 的简单接口测试。
    
    Returns:
        (是否有效, 错误信息)
    """
    if not api_key or not api_key.strip():
        return False, "API 密钥不能为空"
    api_key = api_key.strip()
    try:
        from dashscope import TextEmbedding

        # 使用轻量级 embedding 调用验证
        resp = TextEmbedding.call(
            model="text-embedding-v2",
            input=["test"],
            api_key=api_key,
        )
        if resp.status_code == 200:
            return True, ""
        return False, resp.message or "API 调用失败"
    except Exception as e:
        return False, str(e)
