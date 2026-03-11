"""边界情况与异常处理测试"""

import io
import os
import random
import string
from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def client():
    """创建异步测试客户端"""
    from src.api.main import app
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def auth_headers(client):
    """创建认证头"""
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"edge_user_{random_suffix}"
    await client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123456", "email": f"{username}@example.com"}
    )
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "test123456"}
    )
    token = response.json().get("token")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        try:
            import yaml
            with open("config.yaml") as f:
                api_key = yaml.safe_load(f).get("api", {}).get("dashscope_api_key")
        except Exception:
            pass
    if not api_key:
        api_key = "sk-test-key-for-testing"
    await client.post(
        "/api/user/api-key",
        json={"api_key": api_key},
        headers={"Authorization": f"Bearer {token}"}
    )
    return {"Authorization": f"Bearer {token}"}


# ----- 认证流程边界 -----
@pytest.mark.asyncio
async def test_register_empty_username(client):
    """测试注册 - 空用户名"""
    response = await client.post(
        "/api/auth/register",
        json={"username": "", "password": "test123456", "email": "a@b.com"}
    )
    assert response.status_code == 400
    assert "空" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_register_short_password(client):
    """测试注册 - 密码过短"""
    response = await client.post(
        "/api/auth/register",
        json={"username": "user123", "password": "12345", "email": "a@b.com"}
    )
    assert response.status_code == 400
    assert "6" in response.json().get("detail", "") or "密码" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_login_user_not_found(client):
    """测试登录 - 用户不存在"""
    response = await client.post(
        "/api/auth/login",
        json={"username": "nonexistent_user_xyz", "password": "test123456"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """测试登录 - 密码错误"""
    import random
    import string
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    username = f"wrongpwd_{suffix}"
    await client.post(
        "/api/auth/register",
        json={"username": username, "password": "correct123", "email": f"{username}@b.com"}
    )
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "wrongpassword"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_review_without_token(client):
    """测试审核 - 无 token"""
    response = await client.post(
        "/api/review",
        json={"content": "测试内容"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_review_with_invalid_token(client):
    """测试审核 - 无效 token"""
    response = await client.post(
        "/api/review",
        json={"content": "测试内容"},
        headers={"Authorization": "Bearer invalid.jwt.token"}
    )
    assert response.status_code == 401


# ----- API 密钥相关 -----
@pytest.mark.asyncio
async def test_api_key_empty(client, auth_headers):
    """测试保存空 API 密钥"""
    response = await client.post(
        "/api/user/api-key",
        json={"api_key": ""},
        headers=auth_headers
    )
    assert response.status_code == 400


# ----- JWT 过期 -----
@pytest.mark.asyncio
async def test_review_with_expired_token(client, auth_headers):
    """测试审核 - 过期 token 返回 401"""
    from datetime import timedelta
    from src.auth import create_access_token
    import os

    # 使用极短过期时间生成 token
    secret = os.getenv("AUTH_SECRET_KEY") or "your-secret-key-change-in-production"
    expired_token = create_access_token(
        {"sub": "999", "username": "expired_user"},
        secret,
        expires_delta=timedelta(seconds=-10),
    )
    response = await client.post(
        "/api/review",
        json={"content": "测试内容"},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


# ----- 多模态格式错误 -----
@pytest.mark.asyncio
async def test_multimodal_image_size_limit(client, auth_headers):
    """测试多模态 - 图片超过大小限制"""
    # 创建超过 5MB 的假图片数据
    large_data = b"x" * (6 * 1024 * 1024)  # 6MB
    files = {"images": ("large.png", io.BytesIO(large_data), "image/png")}
    response = await client.post(
        "/api/review-multimodal",
        data={"text": "有文本"},
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 413
    assert "MB" in response.json().get("detail", "") or "大小" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_multimodal_invalid_file_type(client, auth_headers):
    """测试多模态 - 非图片文件"""
    files = {
        "images": ("test.txt", io.BytesIO(b"not an image"), "text/plain")
    }
    response = await client.post(
        "/api/review-multimodal",
        data={"text": "有文本"},
        files=files,
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "图片" in response.json().get("detail", "")


# ----- 文本审核边界 -----
@patch("src.reviewer.call_llm_json")
def test_reviewer_unicode_special_chars(mock_llm):
    """测试审核 - Unicode 特殊字符"""
    from src.reviewer import ContentReviewer

    mock_llm.return_value = {
        "compliance": True,
        "violation_type": None,
        "cited_articles": [],
        "confidence": 0.9,
        "reasoning": "合规",
    }
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    content = "保险产品介绍 \u200b\u200c\u200d\u2060 零宽字符测试"
    result = reviewer.review(content)
    assert "compliance" in result


@patch("src.reviewer.call_llm_json")
def test_reviewer_very_long_reasoning(mock_llm):
    """测试审核 - LLM 返回超长 reasoning"""
    from src.reviewer import ContentReviewer

    mock_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "cited_articles": [],
        "confidence": 0.95,
        "reasoning": "A" * 10000,
    }
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("收益10%稳赚")
    assert result["compliance"] is False
    assert len(result["reasoning"]) > 0


@patch("src.reviewer.call_llm_json")
def test_reviewer_llm_exception(mock_llm):
    """测试审核 - LLM 调用异常"""
    from src.reviewer import ContentReviewer

    mock_llm.side_effect = ConnectionError("网络错误")
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("某内容")
    assert result["compliance"] is False
    assert "异常" in result.get("reasoning", "") or "失败" in result.get("reasoning", "")


# ----- 评估器边界 -----
def test_evaluator_empty_predictions():
    """测试评估器 - 空预测列表"""
    from src.evaluator import Evaluator

    evaluator = Evaluator()
    test_cases = []
    predictions = []
    result = evaluator.evaluate(test_cases, predictions)
    assert result["summary"]["total_cases"] == 0
    assert result["summary"]["accuracy"] == 0.0
