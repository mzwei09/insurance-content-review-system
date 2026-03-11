"""FastAPI 主入口 - 审核接口、认证、API密钥管理、静态前端"""

from __future__ import annotations

import logging
from typing import Optional
import os
from datetime import timedelta
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import api_key_manager, auth
from ..api_key_manager import verify_api_key as verify_dashscope_key
from ..auth import verify_token
from ..database import get_engine, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


# Pydantic models at module level for proper FastAPI body inference
class ReviewRequest(BaseModel):
    content: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class APIKeyRequest(BaseModel):
    api_key: str
import time
from contextlib import asynccontextmanager

_reviewer = None
_multimodal_reviewer = None
_logger = logging.getLogger("aireview.api")
security = HTTPBearer(auto_error=False)


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_auth_config() -> tuple[str, str, int]:
    cfg = _load_config()
    auth_cfg = cfg.get("auth", {})
    secret = auth_cfg.get("secret_key", "your-secret-key-change-in-production")
    algo = auth_cfg.get("algorithm", "HS256")
    expire_min = auth_cfg.get("access_token_expire_minutes", 1440)
    return secret, algo, expire_min


def _get_db_url() -> str:
    # 优先使用环境变量（用于测试隔离）
    env_db_url = os.environ.get("DATABASE_URL")
    if env_db_url:
        return env_db_url
    
    cfg = _load_config()
    db_cfg = cfg.get("database", {})
    url = db_cfg.get("url", "")
    root = Path(__file__).resolve().parent.parent.parent
    if url and "sqlite" in url:
        # 解析相对路径为绝对路径
        if "sqlite:///" in url:
            rel = url.replace("sqlite:///", "")
            if not Path(rel).is_absolute():
                abs_path = (root / rel).resolve()
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                return f"sqlite:///{abs_path}"
        return url
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / 'users.db'}"


def _get_reviewer():
    global _reviewer
    if _reviewer is not None:
        return _reviewer
    from ..reviewer import ContentReviewer
    from ..retriever import Retriever
    from ..vectorstore import VectorStore

    cfg = _load_config()
    vs_cfg = cfg.get("vectorstore", {})
    ret_cfg = cfg.get("retriever", {})
    llm_cfg = cfg.get("llm", {})

    api_cfg = cfg.get("api", {})
    root = Path(__file__).resolve().parent.parent.parent
    index_path = vs_cfg.get("index_path", "data/vectorstore/faiss.index")
    metadata_path = vs_cfg.get("metadata_path", "data/vectorstore/metadata.json")
    if not Path(index_path).is_absolute():
        index_path = str(root / index_path)
    if not Path(metadata_path).is_absolute():
        metadata_path = str(root / metadata_path)
    vectorstore = VectorStore(
        dimension=vs_cfg.get("dimension", 1536),
        embedding_model=api_cfg.get("embedding_model") or vs_cfg.get("embedding_model", "text-embedding-v2"),
        index_path=index_path,
        metadata_path=metadata_path,
    )
    if not vectorstore.load():
        vectorstore = None

    retriever = Retriever(vectorstore, **ret_cfg) if vectorstore else None
    model = api_cfg.get("model_name") or llm_cfg.get("model", "qwen-max")
    _reviewer = ContentReviewer(
        vectorstore=vectorstore,
        retriever=retriever,
        model=model,
        config=cfg,
    )
    return _reviewer


def _get_multimodal_reviewer():
    """获取多模态审核器（支持图文混合）"""
    global _multimodal_reviewer
    if _multimodal_reviewer is not None:
        return _multimodal_reviewer
    from ..multimodal_reviewer import MultimodalReviewer
    from ..retriever import Retriever
    from ..vectorstore import VectorStore

    cfg = _load_config()
    vs_cfg = cfg.get("vectorstore", {})
    ret_cfg = cfg.get("retriever", {})
    llm_cfg = cfg.get("llm", {})
    api_cfg = cfg.get("api", {})

    root = Path(__file__).resolve().parent.parent.parent
    index_path = vs_cfg.get("index_path", "data/vectorstore/faiss.index")
    metadata_path = vs_cfg.get("metadata_path", "data/vectorstore/metadata.json")
    if not Path(index_path).is_absolute():
        index_path = str(root / index_path)
    if not Path(metadata_path).is_absolute():
        metadata_path = str(root / metadata_path)
    vectorstore = VectorStore(
        dimension=vs_cfg.get("dimension", 1536),
        embedding_model=api_cfg.get("embedding_model") or vs_cfg.get("embedding_model", "text-embedding-v2"),
        index_path=index_path,
        metadata_path=metadata_path,
    )
    if not vectorstore.load():
        vectorstore = None

    retriever = Retriever(vectorstore, **ret_cfg) if vectorstore else None
    model = api_cfg.get("model_name") or llm_cfg.get("model", "qwen-max")
    multimodal_model = api_cfg.get("multimodal_model", "qwen-vl-max")
    _multimodal_reviewer = MultimodalReviewer(
        vectorstore=vectorstore,
        retriever=retriever,
        model=model,
        config=cfg,
        multimodal_model=multimodal_model,
    )
    return _multimodal_reviewer


def _adapt_review_result(raw: dict) -> dict:
    """将 reviewer 输出适配为 API 规范格式"""
    if "compliance" in raw:
        # 支持新的 violation_types 数组格式
        violation_types = raw.get("violation_types")
        violation_type = raw.get("violation_type", "") or ""
        
        # 如果有 violation_types 数组，优先使用
        if violation_types and isinstance(violation_types, list):
            violation_type = violation_types[0] if violation_types else ""
        
        result = {
            "compliance": raw["compliance"],
            "violation_types": violation_types,  # 新增：多违规类型数组
            "violation_type": violation_type,     # 保留：向后兼容
            "cited_articles": raw.get("cited_articles", []),
            "confidence": float(raw.get("confidence", 0.8)),
            "reasoning": raw.get("reasoning", "") or "",
        }
        
        # 保留详细审核结果（如果有）
        if "text_result" in raw:
            result["text_result"] = raw["text_result"]
        if "image_results" in raw:
            result["image_results"] = raw["image_results"]
        
        return result
        
    is_violation = raw.get("is_violation", False)
    return {
        "compliance": not is_violation,
        "violation_types": None,
        "violation_type": raw.get("violation_type", "") or "",
        "cited_articles": raw.get("cited_articles", []),
        "confidence": float(raw.get("confidence", 0.8)),
        "reasoning": (raw.get("reason", "") or raw.get("suggestion", "") or ""),
    }


def _dev_mode_api_key() -> Optional[str]:
    """开发者模式已禁用，始终返回None，强制用户在前端配置API密钥"""
    # 开发者模式已禁用，所有用户必须注册、登录并在前端配置API密钥
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """
    获取当前用户。支持两种模式：
    1. 开发者模式：无 token 且 .env 有 DASHSCOPE_API_KEY 时返回 None（表示使用 env 密钥）
    2. 正常模式：需要有效 JWT，返回用户信息
    """
    if credentials and credentials.credentials:
        token = credentials.credentials
        secret, algo, _ = _get_auth_config()
        payload = verify_token(token, secret, algo)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = auth.get_user_by_id(int(user_id), _get_db_url())
                if user:
                    return {"id": user.id, "username": user.username, "email": user.email or ""}
    return None


async def get_current_user_required(
    current_user: Optional[dict] = Depends(get_current_user),
):
    """需要登录的接口使用此依赖。开发者模式下允许无用户。"""
    if current_user is not None:
        return current_user
    if _dev_mode_api_key():
        return {"id": None, "username": "developer", "email": ""}  # 开发者模式
    raise HTTPException(status_code=401, detail="请先登录")


def _resolve_api_key_for_review(current_user: Optional[dict], required: bool = True) -> Optional[str]:
    """解析审核时使用的 API 密钥：用户密钥 或 开发者模式 env 密钥"""
    if current_user and current_user.get("id"):
        key = api_key_manager.get_api_key(current_user["id"], _get_db_url())
        if key:
            return key
        if required:
            raise HTTPException(status_code=400, detail="请先在个人中心配置百炼 API 密钥")
        return None
    if _dev_mode_api_key():
        return _dev_mode_api_key()
    if required:
        raise HTTPException(status_code=401, detail="请先登录")
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("Initializing database...")
    db_url = _get_db_url()
    if db_url:
        engine = get_engine(db_url)
        init_db(engine)
    _logger.info("Loading reviewer at startup...")
    try:
        _get_reviewer()
        _logger.info("Reviewer loaded successfully")
    except Exception as e:
        _logger.warning("Reviewer load failed (will retry on first request): %s", e)
    yield
    pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="保险营销内容智能审核系统",
        description="基于大模型的保险营销内容合规审核 API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        _logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        _logger.exception("Unhandled exception: %s", exc)
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail} if isinstance(exc.detail, str) else {"detail": exc.detail},
            )
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误"},
        )

    # ----- Auth routes -----
    @app.post("/api/auth/register")
    async def register(req: RegisterRequest):
        if not req.username.strip():
            raise HTTPException(status_code=400, detail="用户名不能为空")
        if not req.password or len(req.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少6位")
        try:
            user = auth.register(req.username.strip(), req.password, req.email, _get_db_url())
            secret, algo, expire_min = _get_auth_config()
            token = auth.create_access_token(
                {"sub": str(user.id), "username": user.username},
                secret,
                algo,
                timedelta(minutes=expire_min),
            )
            return {
                "success": True,
                "token": token,
                "user": {"id": user.id, "username": user.username, "email": user.email or ""},
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/auth/login")
    async def login(req: LoginRequest):
        user, error_code = auth.authenticate(req.username, req.password, _get_db_url())
        if not user:
            if error_code == "user_not_found":
                raise HTTPException(status_code=404, detail="用户不存在，请先注册")
            elif error_code == "wrong_password":
                raise HTTPException(status_code=401, detail="密码错误")
            else:
                raise HTTPException(status_code=401, detail="用户名或密码错误")
        secret, algo, expire_min = _get_auth_config()
        token = auth.create_access_token(
            {"sub": str(user.id), "username": user.username},
            secret,
            algo,
            timedelta(minutes=expire_min),
        )
        return {
            "success": True,
            "token": token,
            "user": {"id": user.id, "username": user.username, "email": user.email or ""},
        }

    @app.get("/api/auth/me")
    async def get_me(current_user: Optional[dict] = Depends(get_current_user)):
        if not current_user:
            if _dev_mode_api_key():
                return {"success": True, "user": {"username": "developer", "email": "", "dev_mode": True}}
            raise HTTPException(status_code=401, detail="未登录")
        return {"success": True, "user": current_user}

    # ----- API Key routes -----
    @app.post("/api/user/api-key")
    async def save_user_api_key(
        req: APIKeyRequest,
        current_user: dict = Depends(get_current_user_required),
    ):
        if not current_user.get("id"):
            raise HTTPException(status_code=400, detail="开发者模式请在 .env 配置密钥")
        if not req.api_key.strip():
            raise HTTPException(status_code=400, detail="API 密钥不能为空")
        api_key_manager.save_api_key(current_user["id"], req.api_key, _get_db_url())
        return {"success": True, "message": "API 密钥已保存"}

    @app.get("/api/user/api-key")
    async def get_user_api_key(
        current_user: dict = Depends(get_current_user_required),
    ):
        if not current_user.get("id"):
            return {"success": True, "api_key_masked": None, "configured": False}
        masked = api_key_manager.get_api_key_masked(current_user["id"], _get_db_url())
        return {"success": True, "api_key_masked": masked, "configured": masked is not None}

    @app.put("/api/user/api-key")
    async def update_user_api_key(
        req: APIKeyRequest,
        current_user: dict = Depends(get_current_user_required),
    ):
        if not current_user.get("id"):
            raise HTTPException(status_code=400, detail="开发者模式请在 .env 配置密钥")
        if not req.api_key.strip():
            raise HTTPException(status_code=400, detail="API 密钥不能为空")
        api_key_manager.update_api_key(current_user["id"], req.api_key, _get_db_url())
        return {"success": True, "message": "API 密钥已更新"}

    @app.delete("/api/user/api-key")
    async def delete_user_api_key(
        current_user: dict = Depends(get_current_user_required),
    ):
        if not current_user.get("id"):
            raise HTTPException(status_code=400, detail="开发者模式无个人密钥")
        api_key_manager.delete_api_key(current_user["id"], _get_db_url())
        return {"success": True, "message": "API 密钥已删除"}

    @app.post("/api/user/api-key/verify")
    async def verify_user_api_key(
        req: APIKeyRequest,
        current_user: dict = Depends(get_current_user_required),
    ):
        if not req.api_key.strip():
            raise HTTPException(status_code=400, detail="API 密钥不能为空")
        ok, msg = verify_dashscope_key(req.api_key)
        if ok:
            return {"success": True, "valid": True, "message": "验证通过"}
        return {"success": True, "valid": False, "message": msg}

    # ----- Review (requires auth or dev mode) -----
    @app.post("/api/review")
    async def review(
        body: ReviewRequest,
        current_user: dict = Depends(get_current_user_required),
    ):
        if not body.content.strip():
            raise HTTPException(status_code=400, detail="内容不能为空")
        api_key = _resolve_api_key_for_review(current_user)
        if not api_key:
            raise HTTPException(status_code=400, detail="请先在个人中心配置百炼 API 密钥")
        try:
            reviewer = _get_reviewer()
            raw = reviewer.review(body.content, api_key=api_key)
            data = _adapt_review_result(raw)
            if current_user and current_user.get("id"):
                api_key_manager.update_last_used(current_user["id"], _get_db_url())
            return {"success": True, "data": data, "error": None}
        except ValueError as e:
            error_msg = str(e)
            # 检查是否是 API 密钥错误
            if "401" in error_msg or "invalid_api_key" in error_msg or "Incorrect API key" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="API 密钥无效或已过期，请在个人中心重新配置正确的百炼 API 密钥"
                )
            raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            _logger.exception("Review failed: %s", e)
            error_msg = str(e)
            # 检查是否是 API 密钥错误
            if "401" in error_msg or "invalid_api_key" in error_msg or "Incorrect API key" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="API 密钥无效或已过期，请在个人中心重新配置正确的百炼 API 密钥"
                )
            raise HTTPException(status_code=500, detail=f"审核服务异常：{error_msg}")

    @app.post("/api/review-multimodal")
    async def review_multimodal(
        text: str = Form(""),
        images: list[UploadFile] = File(default=[]),
        current_user: dict = Depends(get_current_user_required),
    ):
        """图文混合审核：支持文本 + 多图片上传"""
        text_content = (text or "").strip()
        if not text_content and not images:
            raise HTTPException(status_code=400, detail="请至少输入文本或上传图片")
        api_key = _resolve_api_key_for_review(current_user)
        if not api_key:
            raise HTTPException(status_code=400, detail="请先在个人中心配置百炼 API 密钥")

        image_urls = []
        for uploaded in images:
            if not uploaded.filename or not uploaded.content_type:
                continue
            if not (uploaded.content_type.startswith("image/")):
                raise HTTPException(
                    status_code=400,
                    detail=f"请上传图片文件，当前类型：{uploaded.content_type}",
                )
            try:
                data = await uploaded.read()
                if not data:
                    continue
                import base64
                b64 = base64.b64encode(data).decode("utf-8")
                mime = uploaded.content_type or "image/jpeg"
                image_urls.append(f"data:{mime};base64,{b64}")
            except Exception as e:
                _logger.warning("Read image failed: %s", e)
                raise HTTPException(status_code=400, detail=f"图片读取失败：{e}")

        try:
            reviewer = _get_multimodal_reviewer()
            raw = reviewer.review(
                content=text_content,
                image_urls=image_urls if image_urls else None,
                api_key=api_key,
            )
            data = _adapt_review_result(raw)
            if current_user and current_user.get("id"):
                api_key_manager.update_last_used(current_user["id"], _get_db_url())
            return {"success": True, "data": data, "error": None}
        except ValueError as e:
            error_msg = str(e)
            # 检查是否是 API 密钥错误
            if "401" in error_msg or "invalid_api_key" in error_msg or "Incorrect API key" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="API 密钥无效或已过期，请在个人中心重新配置正确的百炼 API 密钥"
                )
            raise HTTPException(status_code=400, detail=error_msg)
        except Exception as e:
            _logger.exception("Multimodal review failed: %s", e)
            error_msg = str(e)
            # 检查是否是 API 密钥错误
            if "401" in error_msg or "invalid_api_key" in error_msg or "Incorrect API key" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="API 密钥无效或已过期，请在个人中心重新配置正确的百炼 API 密钥"
                )
            raise HTTPException(status_code=500, detail=f"审核服务异常：{error_msg}")

    @app.get("/api/auth/check")
    async def auth_check():
        """检查认证状态，用于前端判断是否可访问审核（含开发者模式）"""
        if _dev_mode_api_key():
            return {"authenticated": True, "dev_mode": True, "user": {"username": "developer"}}
        return {"authenticated": False, "dev_mode": False}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
