# 文档与系统验证清单

> 用于验证文档准确性及系统可运行性

## 一、链接验证

| 链接 | 目标文件 | 状态 |
|------|----------|------|
| [架构文档](architecture.md) | docs/architecture.md | ✅ |
| [项目结构](../PROJECT_STRUCTURE.md) | PROJECT_STRUCTURE.md | ✅ |
| [验收指南](../ACCEPTANCE_GUIDE.md) | ACCEPTANCE_GUIDE.md | ✅ |
| [截图指引](SCREENSHOT_GUIDE.md) | docs/SCREENSHOT_GUIDE.md | ✅ |

## 二、命令验证

| 命令 | 预期结果 |
|------|----------|
| `bash start.sh --help` | 显示帮助信息 |
| `bash start.sh --port 8001` | 使用 8001 端口启动 |
| `PORT=8001 bash start.sh` | 使用环境变量指定端口 |
| `python scripts/run_evaluation.py` | 生成 reports/evaluation_report.html |
| `pytest tests/ -v` 或 `python -m pytest tests/ -v` | 运行所有测试 |
| `python scripts/build_knowledge_base.py` | 构建/更新知识库 |
| `python scripts/reset_database.py` | 重置用户数据库 |

## 三、路径验证

| 路径 | 说明 |
|------|------|
| `config.yaml` | 项目根目录 |
| `data/vectorstore/faiss.index` | 向量库索引 |
| `data/users.db` | 用户数据库 |
| `frontend/index.html` | 前端入口 |
| `prompts/review_prompt.txt` | 审核 Prompt |
| `logs/app.log` | 应用日志（运行时生成） |
| `reports/evaluation_report.html` | 评估报告（脚本生成） |

## 四、配置验证

| 配置项 | 位置 | 说明 |
|--------|------|------|
| `server.port` | config.yaml | start.sh 可正确解析 |
| `api.model_name` | config.yaml | 默认 qwen-max |
| `api.multimodal_model` | config.yaml | 默认 qwen-vl-max |
| `auth.secret_key` | config.yaml | 生产环境需修改 |

## 五、版本一致性

| 项目 | 文档中的版本 |
|------|---------------|
| Python | 3.9+ |
| FastAPI | 0.104+ |
| License | MIT |

---

**验证日期**：_____________  
**验证人**：_____________
