"""加密工具单元测试"""

import os
from unittest.mock import patch

import pytest


def test_encrypt_decrypt_roundtrip():
    """测试加密解密往返 - 需配置 API_KEY_ENCRYPTION_KEY"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")
    key = Fernet.generate_key().decode()
    with patch.dict(os.environ, {"API_KEY_ENCRYPTION_KEY": key}, clear=False):
        # 清除模块级缓存，强制重新读取 env
        import src.crypto_utils as cu
        if hasattr(cu, "_ENCRYPTION_KEY"):
            cu._ENCRYPTION_KEY = None
        encrypted = cu.encrypt_api_key("sk-test-key-12345")
        assert encrypted is not None
        assert encrypted != "sk-test-key-12345"
        decrypted = cu.decrypt_api_key(encrypted)
        assert decrypted == "sk-test-key-12345"


def test_encrypt_without_key_returns_none():
    """未配置密钥时加密返回 None"""
    import src.crypto_utils as cu
    if hasattr(cu, "_ENCRYPTION_KEY"):
        cu._ENCRYPTION_KEY = None
    with patch.dict(os.environ, {"API_KEY_ENCRYPTION_KEY": ""}, clear=False):
        encrypted = cu.encrypt_api_key("sk-test")
        assert encrypted is None


def test_decrypt_plaintext_returns_none():
    """解密明文（非加密格式）时返回 None，调用方应使用原值"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")
    key = Fernet.generate_key().decode()
    with patch.dict(os.environ, {"API_KEY_ENCRYPTION_KEY": key}, clear=False):
        import src.crypto_utils as cu
        if hasattr(cu, "_ENCRYPTION_KEY"):
            cu._ENCRYPTION_KEY = None
        # 传入明文（未加密的 sk- 格式）
        decrypted = cu.decrypt_api_key("sk-plain-text-key")
        assert decrypted is None
