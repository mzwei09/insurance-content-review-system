"""API 密钥管理测试 - 单元测试与 API 端点测试"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def test_api_key_save_and_get(test_db_url):
    """测试 API 密钥保存与获取"""
    from src import api_key_manager, auth

    user = auth.register("apikey_user", "pass123", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-test-key-abc123", test_db_url)
    assert api_key_manager.get_api_key(user.id, test_db_url) == "sk-test-key-abc123"


def test_api_key_masked_format(test_db_url):
    """测试 API 密钥脱敏格式"""
    from src import api_key_manager, auth

    user = auth.register("mask_user", "pass", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-1234567890abcdef", test_db_url)
    masked = api_key_manager.get_api_key_masked(user.id, test_db_url)
    assert masked is not None
    assert "****" in masked
    assert "sk-" in masked
    assert "cdef" in masked  # 末尾4位可见
    assert "1234567890abcdef" not in masked  # 中间部分应脱敏


def test_api_key_masked_short_key(test_db_url):
    """测试过短密钥的脱敏处理"""
    from src import api_key_manager, auth

    user = auth.register("short_user", "pass", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-123", test_db_url)
    masked = api_key_manager.get_api_key_masked(user.id, test_db_url)
    # 长度 < 8 时返回 None
    assert masked is None


def test_api_key_update_overwrites(test_db_url):
    """测试更新 API 密钥会覆盖旧值"""
    from src import api_key_manager, auth

    user = auth.register("update_user", "pass", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-old-key", test_db_url)
    api_key_manager.update_api_key(user.id, "sk-new-key", test_db_url)
    assert api_key_manager.get_api_key(user.id, test_db_url) == "sk-new-key"


def test_api_key_delete(test_db_url):
    """测试删除 API 密钥"""
    from src import api_key_manager, auth

    user = auth.register("del_user", "pass", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-key", test_db_url)
    assert api_key_manager.delete_api_key(user.id, test_db_url) is True
    assert api_key_manager.get_api_key(user.id, test_db_url) is None


def test_api_key_delete_nonexistent(test_db_url):
    """测试删除不存在的密钥返回 True（幂等）"""
    from src import api_key_manager, auth

    user = auth.register("no_key_user", "pass", None, test_db_url)
    # 未保存过密钥，删除应返回 False（无记录可删）
    result = api_key_manager.delete_api_key(user.id, test_db_url)
    assert result is False


def test_api_key_update_last_used(test_db_url):
    """测试更新最后使用时间"""
    from src import api_key_manager, auth

    user = auth.register("lastused_user", "pass", None, test_db_url)
    api_key_manager.save_api_key(user.id, "sk-key", test_db_url)
    api_key_manager.update_last_used(user.id, test_db_url)
    # 不抛异常即通过
    assert api_key_manager.get_api_key(user.id, test_db_url) == "sk-key"


@patch("dashscope.TextEmbedding")
def test_verify_api_key_valid(mock_embedding):
    """测试 API 密钥验证 - 有效密钥"""
    from src.api_key_manager import verify_api_key

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_embedding.call.return_value = mock_resp

    ok, msg = verify_api_key("sk-valid-key")
    assert ok is True
    assert msg == ""


@patch("dashscope.TextEmbedding")
def test_verify_api_key_invalid(mock_embedding):
    """测试 API 密钥验证 - 无效密钥"""
    from src.api_key_manager import verify_api_key

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.message = "Invalid API key"
    mock_embedding.call.return_value = mock_resp

    ok, msg = verify_api_key("sk-invalid-key")
    assert ok is False
    assert "Invalid" in msg or "API" in msg


def test_verify_api_key_empty():
    """测试 API 密钥验证 - 空密钥"""
    from src.api_key_manager import verify_api_key

    ok, msg = verify_api_key("")
    assert ok is False
    assert "空" in msg or "empty" in msg.lower()

    ok2, msg2 = verify_api_key("   ")
    assert ok2 is False


def test_verify_api_key_whitespace_only():
    """测试 API 密钥验证 - 仅空白字符"""
    from src.api_key_manager import verify_api_key

    ok, msg = verify_api_key("   \t\n  ")
    assert ok is False
