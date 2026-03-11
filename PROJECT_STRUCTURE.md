# 项目结构说明

本文档帮助开发者快速理解代码组织与各目录职责。

## 目录树

```
aireviewsystem/
├── README.md                    # 项目主文档
├── LICENSE                      # MIT 许可证
├── requirements.txt             # Python 依赖
├── config.yaml                  # 系统配置（模型、向量库、认证等）
├── start.sh                     # 一键启动脚本
├── .env.example                 # 环境变量模板
├── .gitignore                   # Git 忽略规则
├── pytest.ini                   # pytest 配置
│
├── src/                         # 核心源代码
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py              # FastAPI 入口、路由定义
│   ├── auth.py                  # 用户认证（注册、登录、JWT）
│   ├── api_key_manager.py      # 用户 API 密钥管理
│   ├── database.py              # SQLAlchemy 模型与初始化
│   ├── document_parser.py       # 文档解析（PDF/DOC/DOCX）
│   ├── vectorstore.py           # FAISS 向量库
│   ├── retriever.py             # RAG 检索
│   ├── llm_client.py            # 百炼大模型 API 客户端
│   ├── reviewer.py              # 文本合规审核核心
│   ├── multimodal_reviewer.py  # 图文混合审核
│   └── evaluator.py             # 效果评估
│
├── prompts/
│   └── review_prompt.txt        # 审核 Prompt 模板
│
├── scripts/                     # 工具脚本
│   ├── init_database.py         # 初始化数据库
│   ├── reset_database.py       # 重置用户数据库
│   ├── build_knowledge_base.py  # 构建向量库
│   ├── run_evaluation.py        # 运行评估
│   └── start_server.sh         # 开发模式启动（热重载）
│
├── tests/                       # 测试代码
│   ├── __init__.py
│   ├── conftest.py              # pytest  fixtures
│   ├── test_auth.py             # 认证与 API 密钥测试
│   ├── test_reviewer.py         # 审核逻辑单元测试
│   ├── test_integration.py      # 集成测试
│   └── test_evaluator.py        # 评估器测试
│
├── data/                        # 数据目录
│   ├── documents/               # 监管文档（PDF/DOCX，需自行准备）
│   ├── knowledge_base.json      # 知识库 JSON（可选）
│   ├── vectorstore/             # 向量库存储（faiss.index，由脚本生成）
│   └── test_cases/              # 测试用例
│       └── test_cases.json
│
├── frontend/
│   ├── index.html               # 前端界面（纯 HTML + Tailwind）
│   └── UX_IMPROVEMENTS.md       # 前端优化说明
│
├── docs/                        # 文档
│   ├── architecture.md         # 系统架构
│   └── PERFORMANCE_ANALYSIS.md  # 性能分析
│
├── test_images/                 # 测试图片
│   └── README.md                # 测试图片说明
│
├── ACCEPTANCE_GUIDE.md          # 验收指南
├── CHANGELOG.md                 # 版本变更记录
└── PROJECT_STRUCTURE.md         # 本文件
```

## 核心模块说明

| 模块 | 职责 |
|------|------|
| `src/api/main.py` | FastAPI 应用、路由、中间件 |
| `src/reviewer.py` | 文本审核：RAG 检索 + 大模型推理 |
| `src/multimodal_reviewer.py` | 图文审核：图片 OCR + 文本审核 |
| `src/vectorstore.py` | FAISS 向量存储与相似度检索 |
| `src/retriever.py` | 根据查询检索相关监管条文 |
| `src/llm_client.py` | 百炼 API 调用（chat、embedding） |
| `src/auth.py` | 用户注册、登录、JWT 签发与验证 |
| `src/api_key_manager.py` | 用户个人 API 密钥的存储与验证 |

## 数据流

1. **知识库构建**：`scripts/build_knowledge_base.py` 读取 `data/documents/` 中的 PDF/DOCX，解析后向量化，输出到 `data/vectorstore/`
2. **审核请求**：用户输入 → `retriever.retrieve()` 检索条文 → `reviewer.review()` 构造 Prompt → `llm_client` 调用大模型 → 返回 JSON
3. **用户数据**：`data/users.db`（SQLite），存储用户与 API 密钥

## 忽略的文件（.gitignore）

- `data/users.db`：用户数据库
- `data/vectorstore/`：向量库（由脚本生成）
- `data/test/`：测试用数据库
- `logs/`：日志
- `reports/`：评估报告
- `.env`：环境变量（含密钥）
- `venv/`、`__pycache__/`：虚拟环境与缓存
