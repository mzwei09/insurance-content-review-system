"""API 集成测试 - 使用 pytest + httpx 测试审核接口"""

import io
import os
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
    import random
    import string
    
    # 生成随机用户名避免冲突
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"test_user_{random_suffix}"
    
    # 注册新用户
    await client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123456", "email": f"{username}@example.com"}
    )
    
    # 登录获取token
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "test123456"}
    )
    data = response.json()
    token = data.get("token")
    
    # 配置真实的API密钥（从环境变量或config.yaml读取）
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        # 尝试从config.yaml读取
        try:
            import yaml
            with open("config.yaml") as f:
                config = yaml.safe_load(f)
                api_key = config.get("api", {}).get("dashscope_api_key")
        except:
            pass
    
    if not api_key:
        # 如果还是没有，使用测试密钥（会导致LLM调用失败，但不影响接口测试）
        api_key = "sk-test-key-for-testing"
    
    await client.post(
        "/api/user/api-key",
        json={"api_key": api_key},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health(client):
    """测试健康检查接口"""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"


@pytest.mark.asyncio
async def test_review_normal_request(client, auth_headers):
    """测试 POST /api/review 正常请求"""
    response = await client.post(
        "/api/review",
        json={"content": "本产品为保障型重疾险，覆盖100种重大疾病，请根据自身需求理性选择。"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "data" in data
    result = data["data"]
    assert "compliance" in result
    assert "violation_type" in result
    assert "cited_articles" in result
    assert "confidence" in result
    assert "reasoning" in result
    assert isinstance(result["compliance"], bool)
    assert isinstance(result["cited_articles"], list)


@pytest.mark.asyncio
async def test_review_empty_content(client, auth_headers):
    """测试空内容"""
    response = await client.post(
        "/api/review",
        json={"content": ""},
        headers=auth_headers
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "空" in data["detail"] or "empty" in data["detail"].lower()


@pytest.mark.asyncio
async def test_review_whitespace_only(client, auth_headers):
    """测试仅空白字符"""
    response = await client.post(
        "/api/review",
        json={"content": "   \n\t  "},
        headers=auth_headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_review_long_content(client, auth_headers):
    """测试超长内容（>10000字符）"""
    long_content = "这是一段测试内容。" * 2000  # 约 10000 字符
    response = await client.post(
        "/api/review",
        json={"content": long_content},
        headers=auth_headers
    )
    # 应能正常处理或返回合理错误，不因长度直接 500
    assert response.status_code in (200, 400, 413, 422)


@pytest.mark.asyncio
async def test_review_special_characters(client, auth_headers):
    """测试特殊字符"""
    special_content = "投保即返现！<script>alert(1)</script> &amp; \"收益\" '高'"
    response = await client.post(
        "/api/review",
        json={"content": special_content},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "data" in data


@pytest.mark.asyncio
async def test_review_missing_content_field(client, auth_headers):
    """测试缺少 content 字段"""
    response = await client.post(
        "/api/review",
        json={},
        headers=auth_headers
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_review_invalid_json(client, auth_headers):
    """测试无效 JSON 体"""
    headers_with_auth = {**auth_headers, "Content-Type": "application/json"}
    response = await client.post(
        "/api/review",
        content="not json",
        headers=headers_with_auth,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_review_multimodal_text_only(client, auth_headers):
    """测试多模态接口 - 仅文本"""
    response = await client.post(
        "/api/review-multimodal",
        data={"text": "本产品为保障型重疾险，覆盖100种重大疾病。"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "data" in data
    result = data["data"]
    assert "compliance" in result
    assert isinstance(result["compliance"], bool)


@pytest.mark.asyncio
async def test_review_multimodal_with_image(client, auth_headers):
    """测试多模态接口 - 图片+文本"""
    # 创建一个简单的测试图片（1x1 PNG）
    import base64
    # 1x1 红色PNG图片的base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    
    files = {
        "images": ("test.png", io.BytesIO(png_data), "image/png")
    }
    data = {
        "text": "查看图片中的保险产品宣传内容"
    }
    
    response = await client.post(
        "/api/review-multimodal",
        data=data,
        files=files,
        headers=auth_headers
    )
    assert response.status_code == 200
    result = response.json()
    assert result.get("success") is True
    assert "data" in result


@pytest.mark.asyncio
async def test_review_multimodal_multiple_images(client, auth_headers):
    """测试多模态接口 - 多图片"""
    import base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    
    files = [
        ("images", ("test1.png", io.BytesIO(png_data), "image/png")),
        ("images", ("test2.png", io.BytesIO(png_data), "image/png"))
    ]
    data = {
        "text": "审核这些图片中的营销内容"
    }
    
    response = await client.post(
        "/api/review-multimodal",
        data=data,
        files=files,
        headers=auth_headers
    )
    assert response.status_code == 200
    result = response.json()
    assert result.get("success") is True


@pytest.mark.asyncio
async def test_review_multimodal_no_content(client, auth_headers):
    """测试多模态接口 - 无文本无图片"""
    response = await client.post(
        "/api/review-multimodal",
        data={},
        headers=auth_headers
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_review_multimodal_images_only(client, auth_headers):
    """测试多模态接口 - 仅图片无文本"""
    import base64
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    files = {
        "images": ("poster.png", io.BytesIO(png_data), "image/png")
    }
    # 文本为空，仅传图片
    response = await client.post(
        "/api/review-multimodal",
        data={"text": ""},
        files=files,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "data" in data


@pytest.mark.asyncio
async def test_auth_me_with_token(client, auth_headers):
    """测试 GET /api/auth/me 有 token 时返回用户信息"""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "user" in data
    assert data["user"].get("username")


@pytest.mark.asyncio
async def test_auth_me_without_token(client):
    """测试 GET /api/auth/me 无 token 时返回 401"""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_api_key_masked(client, auth_headers):
    """测试 GET /api/user/api-key 返回脱敏密钥"""
    response = await client.get("/api/user/api-key", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "api_key_masked" in data or "configured" in data


@pytest.mark.asyncio
async def test_review_without_api_key(client):
    """测试审核 - 用户未配置 API 密钥"""
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"nokey_user_{random_suffix}"
    await client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123456", "email": f"{username}@example.com"}
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "test123456"}
    )
    token = login_resp.json().get("token")
    # 不配置 API 密钥
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        "/api/review",
        json={"content": "测试内容"},
        headers=headers
    )
    assert response.status_code == 400
    assert "API" in response.json().get("detail", "") or "密钥" in response.json().get("detail", "")
