"""认证与 API 密钥管理测试"""

import tempfile
from pathlib import Path

import pytest

from src.database import get_engine, init_db


@pytest.fixture
def test_db_url():
    """每个测试使用独立的临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    import os
    os.close(fd)
    url = f"sqlite:///{path}"
    engine = get_engine(url)
    init_db(engine)
    yield url
    Path(path).unlink(missing_ok=True)


def test_register_and_login(test_db_url):
    """测试用户注册与登录"""
    from src import auth

    # 注册
    user = auth.register("testuser", "password123", "test@example.com", test_db_url)
    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"

    # 重复注册应失败
    with pytest.raises(ValueError, match="用户名已存在"):
        auth.register("testuser", "other", None, test_db_url)

    # 登录
    logged, error = auth.authenticate("testuser", "password123", test_db_url)
    assert logged is not None
    assert error is None
    assert logged.username == "testuser"

    # 错误密码
    user, error = auth.authenticate("testuser", "wrong", test_db_url)
    assert user is None
    assert error == "wrong_password"
    
    # 用户不存在
    user, error = auth.authenticate("nonexist", "password123", test_db_url)
    assert user is None
    assert error == "user_not_found"


def test_jwt_token(test_db_url):
    """测试 JWT 生成与验证"""
    from src import auth

    auth.register("jwtuser", "pass", None, test_db_url)

    secret = "test-secret"
    token = auth.create_access_token({"sub": "1", "username": "jwtuser"}, secret)
    assert token

    payload = auth.verify_token(token, secret)
    assert payload is not None
    assert payload.get("sub") == "1"
    assert payload.get("username") == "jwtuser"

    assert auth.verify_token("invalid", secret) is None
    assert auth.verify_token(token, "wrong-secret") is None


def test_api_key_manager(test_db_url):
    """测试 API 密钥管理"""
    from src import api_key_manager, auth

    user = auth.register("apiuser", "pass", None, test_db_url)
    assert user.id

    db_url = test_db_url

    # 保存
    api_key_manager.save_api_key(user.id, "sk-test-key-12345", db_url)
    assert api_key_manager.get_api_key(user.id, db_url) == "sk-test-key-12345"
    masked = api_key_manager.get_api_key_masked(user.id, db_url)
    assert masked and "****" in masked and "12345" in masked or "sk-" in masked

    # 更新
    api_key_manager.update_api_key(user.id, "sk-new-key-67890", db_url)
    assert api_key_manager.get_api_key(user.id, db_url) == "sk-new-key-67890"

    # 删除
    assert api_key_manager.delete_api_key(user.id, db_url) is True
    assert api_key_manager.get_api_key(user.id, db_url) is None


def test_jwt_token_expired(test_db_url):
    """测试 JWT token 过期后验证返回 None"""
    from datetime import timedelta
    from src import auth

    auth.register("expuser", "pass", None, test_db_url)
    secret = "test-secret"
    # 使用负的 expires_delta 使 token 立即过期
    token = auth.create_access_token(
        {"sub": "1", "username": "expuser"},
        secret,
        expires_delta=timedelta(seconds=-1),
    )
    assert token
    payload = auth.verify_token(token, secret)
    assert payload is None
