# 保险营销内容智能审核系统 - 代码质量与架构评估报告

## 一、问题清单（按优先级排序）

### P0 - 严重

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P0-1 | **API 密钥明文存储** | `database.py:37`, `api_key_manager.py` | `api_key_encrypted` 字段名暗示加密，但实际明文存储用户百炼 API 密钥，存在泄露风险 |
| P0-2 | **JWT 默认密钥不安全** | `main.py:64`, `config.yaml:53` | 默认 `secret_key: "your-secret-key-change-in-production"`，生产环境未修改可导致 token 伪造 |
| P0-3 | **CORS 配置不安全** | `main.py:297-302` | `allow_origins=["*"]` 与 `allow_credentials=True` 组合，浏览器可能拒绝且存在 CSRF 风险 |
| P0-4 | **Prompt 注入风险** | `reviewer.py:271` | 使用 `str.format()` 将用户内容注入 prompt，若内容含 `{content}` 或 `{retrieved_articles}` 会破坏 prompt 结构 |

### P1 - 重要

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P1-1 | **main.py 职责过重** | `main.py` | 单文件 430+ 行，混合配置加载、依赖注入、路由、业务逻辑，违反单一职责 |
| P1-2 | **配置加载重复** | `main.py`, `reviewer.py`, `vectorstore.py` | `_load_config()` 多处重复实现，路径解析逻辑分散 |
| P1-3 | **全局可变状态** | `main.py:47-48` | `_reviewer`、`_multimodal_reviewer` 全局变量，不利于测试和并发 |
| P1-4 | **异常处理过于宽泛** | `main.py:357-365` | 全局 `except Exception` 捕获所有异常，可能掩盖编程错误 |
| P1-5 | **auth 模块死代码** | `auth.py:15-27` | `_get_session_factory`、`get_db_session` 未被使用 |
| P1-6 | **bcrypt 未配置 rounds** | `auth.py:31` | 使用默认 `gensalt()`，未显式设置 work factor，无法随硬件升级调整 |
| P1-7 | **多模态 _fallback_result 格式不一致** | `multimodal_reviewer.py:304-312` | 缺少 `violation_types` 字段，与 API 规范不一致 |
| P1-8 | **集成测试数据库冲突** | `conftest.py`, `test_auth.py` | `use_test_database` 与 `test_db_url` 使用不同数据库，测试隔离不清晰 |

### P2 - 一般

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P2-1 | **import 顺序混乱** | `main.py:43-44` | `import time` 与 `from contextlib import asynccontextmanager` 夹在类定义中间 |
| P2-2 | **魔法数字** | 多处 | 如密码最小长度 6、token 过期 1440 分钟等未提取为常量 |
| P2-3 | **日志敏感信息** | `reviewer.py:250` | 审核内容可能含敏感信息，直接 log 前 200 字符有泄露风险 |
| P2-4 | **类型注解不完整** | 多处 | 部分函数缺少返回类型注解 |

### P3 - 可选

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P3-1 | **多模态审核串行执行** | `multimodal_reviewer.py:214-248` | 逐张图片审核可考虑 ThreadPoolExecutor 并行（已有 import 但未使用） |
| P3-2 | **缺少请求限流** | API 层 | 无 rate limiting，易被滥用 |
| P3-3 | **缺少 API 版本控制** | 路由 | `/api/` 无版本前缀，未来升级兼容性差 |

---

## 二、优化建议

### P0-1: API 密钥加密存储

**方案**：使用 Fernet（cryptography）或 AES 对 API 密钥加密后存储，密钥从环境变量 `API_KEY_ENCRYPTION_KEY` 读取。

```python
# 新增 src/crypto_utils.py
from cryptography.fernet import Fernet
import os

def encrypt_api_key(plain: str, key: bytes = None) -> str:
    fernet = Fernet(key or os.environ["API_KEY_ENCRYPTION_KEY"].encode())
    return fernet.encrypt(plain.encode()).decode()

def decrypt_api_key(encrypted: str, key: bytes = None) -> str:
    fernet = Fernet(key or os.environ["API_KEY_ENCRYPTION_KEY"].encode())
    return fernet.decrypt(encrypted.encode()).decode()
```

**注意**：需数据库迁移，将现有明文转为密文。

### P0-2: 强制生产环境更换密钥

**方案**：启动时检查，若 `secret_key` 为默认值且非开发模式，则拒绝启动并报错。

### P0-3: CORS 安全配置

**方案**：将 `allow_origins` 改为从配置读取的具体域名列表，如 `["https://your-frontend.com"]`；开发环境可单独配置。

### P0-4: Prompt 注入防护

**方案**：使用 `str.replace()` 或模板引擎（如 Jinja2）的转义机制，避免用户内容中的 `{` `}` 被 `format()` 解析。或使用 `string.Template` 的 `$content` 形式。

```python
# 使用 replace 避免 format 解析用户内容
user_prompt = self._user_template.replace("{content}", content).replace("{retrieved_articles}", retrieved_text)
```

---

## 三、架构设计评估

### 优点

- **模块划分清晰**：`reviewer`、`multimodal_reviewer`、`auth`、`database`、`api_key_manager` 职责明确
- **RAG 流程合理**：检索 → 构造 prompt → LLM 推理 → 结果验证，流程清晰
- **继承复用**：`MultimodalReviewer` 继承 `ContentReviewer`，避免重复

### 待改进

- **配置管理**：建议统一 `src/config.py`，集中加载与校验
- **依赖注入**：reviewer 等通过全局函数获取，建议使用 FastAPI 的 `Depends` 或工厂模式
- **数据库会话**：各模块自行 `sessionmaker`，建议统一 `get_db` 依赖

---

## 四、测试覆盖评估

| 模块 | 单元测试 | 集成测试 | 边界/异常 |
|------|----------|----------|-----------|
| auth | ✅ 注册/登录/JWT | - | ✅ 错误密码、用户不存在 |
| reviewer | ✅ mock LLM | ✅ API 调用 | ✅ 空内容、JSON 解析失败 |
| api_key_manager | ✅ CRUD | - | - |
| 多模态 | - | ✅ 文本/图片 | ✅ 无内容 400 |
| evaluator | ✅ 准确率/引用 | - | ✅ 数量不一致 |

**缺失**：auth 模块的 SQL 注入测试、API 的未认证访问测试、reviewer 的 prompt 注入测试。

---

## 五、安全性小结

| 项目 | 状态 | 说明 |
|------|------|------|
| 密码存储 | ✅ | bcrypt 正确使用 |
| JWT | ⚠️ | 需更换默认密钥 |
| API 密钥 | ❌ | 明文存储 |
| SQL 注入 | ✅ | 使用 SQLAlchemy ORM，无拼接 |
| XSS | ⚠️ | 审核内容经 LLM 处理，返回 JSON，前端需正确渲染 |
| 输入验证 | ✅ | Pydantic 校验、空内容检查 |
| CORS | ⚠️ | 已改为可配置，生产环境需指定具体域名 |

---

## 六、已实施的代码改进

### 1. P0-4: Prompt 注入防护（已实现）

**文件**：`src/reviewer.py`

**改动**：将 `str.format(content=..., retrieved_articles=...)` 改为先对用户内容和检索结果中的 `{` `}` 转义为 `{{` `}}`，再使用 `str.replace()` 替换占位符。

**效果**：用户输入如 `收益{retrieved_articles}高` 不再会注入检索条文，避免 prompt 被篡改。新增单元测试 `test_content_reviewer_prompt_injection_safe` 验证。

### 2. P0-2: JWT 密钥安全提示（已实现）

**文件**：`src/api/main.py`, `config.yaml`

**改动**：
- 支持通过环境变量 `AUTH_SECRET_KEY` 覆盖配置
- 启动时若使用默认密钥且未设置 `ALLOW_DEFAULT_SECRET`，记录警告日志

**效果**：部署时更容易发现未更换密钥的问题。

### 3. P0-3: CORS 可配置（已实现）

**文件**：`src/api/main.py`, `config.yaml`

**改动**：新增 `cors_origins` 配置项，从 `config.yaml` 读取允许的域名列表。

**效果**：生产环境可配置 `cors_origins: ["https://your-frontend.com"]`，避免使用 `*`。

### 4. P1-7: 多模态 _fallback_result 格式统一（已实现）

**文件**：`src/multimodal_reviewer.py`

**改动**：`_fallback_result` 返回值增加 `violation_types: None` 字段。

**效果**：与 API 规范一致，便于前端统一处理。

### 5. P2-1: import 顺序整理（已实现）

**文件**：`src/api/main.py`

**改动**：将 `import time`、`from contextlib import asynccontextmanager` 移至文件顶部，按标准库、第三方库分组。

**效果**：代码风格更统一，符合 PEP 8。

### 待后续实施

- **P0-1 API 密钥加密**：需引入 `cryptography`，设计迁移方案，建议单独排期
- **P1-1 模块拆分**：将 `main.py` 拆分为路由、配置、依赖注入等子模块
