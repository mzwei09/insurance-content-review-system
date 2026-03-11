"""加密工具 - API 密钥等敏感数据的加密存储"""

from __future__ import annotations

import base64
import os
from typing import Optional

# Fernet 密钥需 32 字节 base64，可从 Fernet.generate_key() 生成
_ENCRYPTION_KEY: Optional[bytes] = None


def _get_encryption_key() -> Optional[bytes]:
    """获取加密密钥，未配置时返回 None（不加密）"""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY
    key_b64 = os.environ.get("API_KEY_ENCRYPTION_KEY")
    if not key_b64 or not key_b64.strip():
        return None
    try:
        key = base64.urlsafe_b64decode(key_b64.strip().encode())
        if len(key) != 32:
            return None
        _ENCRYPTION_KEY = key
        return key
    except Exception:
        return None


def encrypt_api_key(plain: str) -> Optional[str]:
    """
    加密 API 密钥。若未配置 API_KEY_ENCRYPTION_KEY，返回 None 表示不加密。

    Returns:
        加密后的 base64 字符串，或 None（不加密）
    """
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError:
        return None

    key_bytes = _get_encryption_key()
    if key_bytes is None:
        return None

    # Fernet 需要 32 字节 url-safe base64 编码的密钥
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    fernet = Fernet(fernet_key)
    return fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted: str) -> Optional[str]:
    """
    解密 API 密钥。若解密失败（如未加密的明文），返回 None 表示按明文处理。

    Returns:
        解密后的明文，或 None（表示传入的可能是明文，调用方应直接使用）
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return None

    key_bytes = _get_encryption_key()
    if key_bytes is None:
        return None

    try:
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(fernet_key)
        return fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None


def is_encrypted(value: str) -> bool:
    """
    启发式判断存储值是否为加密格式。
    Fernet 密文通常以 gAAAAA 开头且为 base64。
    百炼 API 密钥通常以 sk- 开头。
    """
    if not value or len(value) < 10:
        return False
    stripped = value.strip()
    # Fernet 密文特征
    if stripped.startswith("gAAAAA") and len(stripped) > 20:
        return True
    # 明文 API 密钥特征
    if stripped.startswith("sk-"):
        return False
    return False
