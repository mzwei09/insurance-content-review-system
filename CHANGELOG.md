# 更新日志

本文档记录项目的版本变更。

## [1.0.0] - 2025-03

### 新增

- 基于 RAG + 大模型的保险营销内容合规审核
- 支持文本与图文混合审核
- 多违规类型检测（7 种违规类型）
- 引用监管条文、置信度评分
- Web 界面（用户注册、登录、API 密钥管理）
- 完整知识库（134 条监管条文）
- 单元测试与集成测试

### 技术栈

- Python 3.9+ / FastAPI / FAISS-CPU
- 百炼大模型 API（qwen-max、qwen-vl-max、text-embedding-v2）
- SQLite + SQLAlchemy
- Tailwind CSS（纯 HTML 前端）
