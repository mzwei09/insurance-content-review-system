# 保险营销内容智能审核系统 - 代码质量与架构评估报告

## 一、问题清单（按优先级排序）

### P0 - 严重

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P0-1 | **API 密钥明文存储** | `database.py:37`, `api_key_manager.py` | `api_key_encrypted` 字段名暗示加密，但实际明文存储用户百炼 API 密钥，数据库泄露将直接暴露所有用户密钥 |
| P0-2 | **JWT 默认密钥不安全** | `main.py:74-76`, `config.yaml:55` | 默认 `secret_key: "your-secret-key-change-in-production"`，生产环境未修改可导致 token 伪造、会话劫持 |
| P0-3 | **CORS 配置不安全** | `config.yaml:62`, `main.py:324-330` | `allow_origins=["*"]` 与 `allow_credentials=True` 组合，存在 CSRF 风险，且部分浏览器会拒绝该配置 |

### P1 - 重要

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P1-1 | **main.py 职责过重** | `src/api/main.py` | 单文件 440+ 行，混合配置加载、依赖注入、路由、业务逻辑，违反单一职责原则 |
| P1-2 | **配置加载重复** | `main.py`, `reviewer.py` | `_load_config()` 多处重复实现，路径解析逻辑分散，修改配置路径需改多处 |
| P1-3 | **全局可变状态** | `main.py:56-57` | `_reviewer`、`_multimodal_reviewer` 全局变量，不利于单元测试隔离和并发场景 |
| P1-4 | **异常处理过于宽泛** | `main.py:348-358` | 全局 `except Exception` 捕获所有异常，可能掩盖编程错误（如 `AttributeError`、`TypeError`） |
| P1-5 | **auth 模块死代码** | `auth.py:14-27` | `_get_session_factory`、`get_db_session` 未被任何模块调用，增加维护负担 |
| P1-6 | **bcrypt 未配置 rounds** | `auth.py:31` | 使用默认 `gensalt()`（约 12 rounds），未显式设置，无法随硬件升级调整安全强度 |
| P1-7 | **图片上传无大小限制** | `main.py:419-424` | 多模态接口未限制单张/总图片大小，恶意用户可上传超大文件导致内存耗尽 |
| P1-8 | **集成测试数据库冲突** | `conftest.py`, `test_auth.py` | `use_test_database` 使用 `data/test/`，`test_db_url` 使用 `tempfile`，测试隔离策略不统一 |

### P2 - 一般

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P2-1 | **魔法数字未提取** | 多处 | 密码最小长度 6、token 过期 1440 分钟、置信度阈值 0.7 等散落代码中 |
| P2-2 | **日志敏感信息** | `reviewer.py:250`, `llm_client.py:104` | 审核内容、prompt 可能含敏感信息，直接 log 有泄露风险 |
| P2-3 | **类型注解不完整** | 多处 | 如 `_load_config()` 返回 `dict` 未标注 value 类型 |
| P2-4 | **ReviewRequest 无长度限制** | `main.py:37-38` | `content: str` 无 `max_length`，超长内容可能导致 LLM 超时或成本激增 |

### P3 - 可选

| 编号 | 问题 | 位置 | 描述 |
|------|------|------|------|
| P3-1 | **多模态审核串行执行** | `multimodal_reviewer.py:214-248` | 逐张图片审核为串行，可考虑 ThreadPoolExecutor 并行提升性能 |
| P3-2 | **缺少请求限流** | API 层 | 无 rate limiting，易被滥用导致 API 成本激增 |
| P3-3 | **缺少 API 版本控制** | 路由 | `/api/` 无版本前缀（如 `/api/v1/`），未来升级兼容性差 |

---

## 二、优化建议

### P0-1: API 密钥加密存储

**方案**：使用 Fernet（cryptography）对 API 密钥加密后存储，加密密钥从环境变量 `API_KEY_ENCRYPTION_KEY` 读取。对已有明文数据做兼容：解密失败时按明文处理，保存时统一加密。

**实施**：新增 `src/crypto_utils.py`，修改 `api_key_manager.py` 的 `save_api_key`/`get_api_key`。

### P0-2: 强制生产环境更换 JWT 密钥

**方案**：启动时检查，若 `secret_key` 为默认值且未设置 `ALLOW_DEFAULT_SECRET`，记录警告（已实现）。可进一步：生产环境直接拒绝启动。

### P0-3: CORS 安全配置

**方案**：生产环境在 `config.yaml` 中设置 `cors_origins: ["https://your-frontend.com"]`，避免 `["*"]`。

### P1-5: 移除 auth 死代码

**方案**：删除 `_get_session_factory` 和 `get_db_session`，各模块已通过 `get_engine(db_url)` + `sessionmaker` 自行管理会话。

### P1-6: bcrypt rounds 显式配置

**方案**：`hash_password` 使用 `bcrypt.gensalt(rounds=12)`，并通过 config 或环境变量 `BCRYPT_ROUNDS` 可配置。

### P1-7: 图片上传大小限制

**方案**：在 `review_multimodal` 中检查 `uploaded.size` 或读取后 `len(data)`，单张限制 5MB，总限制 20MB，超限返回 413。

### P1-4: 异常处理细化

**方案**：全局 handler 中区分 `HTTPException`（直接返回）、`ValueError`（400）、其他 `Exception` 记录后返回 500，避免吞掉 `KeyboardInterrupt` 等。

### P2-1: 提取常量

**方案**：在 `main.py` 或新建 `src/constants.py` 中定义 `MIN_PASSWORD_LENGTH = 6`、`DEFAULT_TOKEN_EXPIRE_MINUTES = 1440` 等。

---

## 三、架构设计评估

### 优点

- **模块划分清晰**：`reviewer`、`multimodal_reviewer`、`auth`、`database`、`api_key_manager` 职责明确
- **RAG 流程合理**：检索 → 构造 prompt → LLM 推理 → 结果验证，流程清晰
- **继承复用**：`MultimodalReviewer` 继承 `ContentReviewer`，避免重复
- **SQL 注入防护**：全程使用 SQLAlchemy ORM，无原始 SQL 拼接
- **Prompt 注入防护**：`reviewer.py` 已对用户内容中的 `{` `}` 转义，避免 format 注入

### 待改进

- **配置管理**：建议统一 `src/config.py`，集中加载与校验
- **依赖注入**：reviewer 通过全局函数获取，建议使用 FastAPI 的 `Depends` 或工厂模式
- **数据库会话**：各模块自行 `sessionmaker`，建议统一 `get_db` 依赖注入

---

## 四、测试覆盖评估

| 模块 | 单元测试 | 集成测试 | 边界/异常 |
|------|----------|----------|-----------|
| auth | ✅ 注册/登录/JWT | - | ✅ 错误密码、用户不存在 |
| reviewer | ✅ mock LLM | ✅ API 调用 | ✅ 空内容、JSON 解析失败、prompt 注入 |
| api_key_manager | ✅ CRUD、脱敏、验证 | - | ✅ 空密钥、过短密钥 |
| 多模态 | ✅ mock 提取 | ✅ 文本/图片 | ✅ 无内容 400、提取失败 |
| evaluator | ✅ 准确率 | - | ✅ 空预测 |

**缺失**：auth 的 SQL 注入测试（ORM 已防护）、API 的 rate limit 测试、reviewer 的超长内容截断测试。

---

## 五、安全性小结

| 项目 | 状态 | 说明 |
|------|------|------|
| 密码存储 | ✅ | bcrypt 正确使用 |
| JWT | ⚠️ | 需更换默认密钥，已支持 AUTH_SECRET_KEY 环境变量 |
| API 密钥 | ❌ | 明文存储，需加密 |
| SQL 注入 | ✅ | 使用 SQLAlchemy ORM |
| XSS | ⚠️ | 返回 JSON，前端需正确渲染 |
| 输入验证 | ✅ | Pydantic 校验、空内容检查 |
| Prompt 注入 | ✅ | 已转义 `{` `}` |
| CORS | ⚠️ | 可配置，生产需指定域名 |
| 文件上传 | ✅ | 已限制单张 5MB、总 20MB |

---

## 六、已实施的代码改进

### 1. P0-1: API 密钥加密存储（已实现）

**文件**：`src/crypto_utils.py`（新增）、`src/api_key_manager.py`、`requirements.txt`

**改动**：
- 新增 `crypto_utils.py`，使用 Fernet 对称加密
- 配置 `API_KEY_ENCRYPTION_KEY` 环境变量后，保存时加密、读取时解密
- 未配置时保持明文存储（向后兼容）
- 新增 `cryptography>=41.0.0` 依赖

**效果**：生产环境配置加密密钥后，数据库泄露不会直接暴露用户 API 密钥。

### 2. P1-5: 移除 auth 死代码（已实现）

**文件**：`src/auth.py`

**改动**：删除未使用的 `_get_session_factory`、`get_db_session`。

**效果**：减少维护负担，避免误导。

### 3. P1-6: bcrypt rounds 显式配置（已实现）

**文件**：`src/auth.py`

**改动**：`hash_password` 使用 `bcrypt.gensalt(rounds=12)`，支持环境变量 `BCRYPT_ROUNDS` 覆盖（限制 10-14）。

**效果**：可随硬件升级调整安全强度。

### 4. P1-7: 图片上传大小限制（已实现）

**文件**：`src/api/main.py`

**改动**：单张图片限制 5MB，多图总大小限制 20MB，超限返回 413。

**效果**：防止恶意上传导致内存耗尽。

### 5. P1-4: 异常处理优化（已实现）

**文件**：`src/api/main.py`

**改动**：全局 handler 中，`HTTPException` 仅记录 info 级别日志，其他异常记录 exception 级别。

**效果**：预期业务异常不再产生堆栈日志，便于排查真实错误。

### 6. P2-1: 提取常量（已实现）

**文件**：`src/api/main.py`

**改动**：提取 `MIN_PASSWORD_LENGTH`、`MAX_IMAGE_SIZE_BYTES`、`MAX_TOTAL_IMAGES_SIZE_BYTES`。

**效果**：魔法数字集中管理，便于调整。
