# 系统架构设计

## 架构概览

系统采用 **RAG（检索增强生成）+ 大模型** 架构，实现保险营销内容的合规审核。

```
用户输入 → 向量检索（FAISS）→ 检索相关监管条文
                                ↓
                    构造 Prompt（内容 + 条文）
                                ↓
                    百炼大模型推理（qwen-max）
                                ↓
            结构化输出（合规判断 + 违规类型 + 引用条文 + 置信度）
```

## 核心流程

1. **文档解析**：解析 PDF/DOC/DOCX 监管文档，提取条文
2. **向量化**：使用百炼 Embedding API 构建 FAISS 索引
3. **RAG 检索**：根据输入内容检索 Top-K 相关条文
4. **大模型推理**：结合检索条文进行合规判断
5. **结果输出**：返回结构化审核结果

## 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| 文档解析 | `document_parser.py` | 解析监管文档，提取条文 |
| 向量库 | `vectorstore.py` | FAISS 向量存储与检索 |
| 检索器 | `retriever.py` | RAG 检索逻辑 |
| 大模型 | `llm_client.py` | 百炼 API 调用 |
| 审核核心 | `reviewer.py` | 文本合规审核 |
| 多模态 | `multimodal_reviewer.py` | 图文混合审核 |
| API | `api/main.py` | FastAPI 接口 |

## 数据流

- **知识库构建**：`data/documents/` → 解析 → `data/vectorstore/faiss.index`
- **审核请求**：用户输入 → 检索 → Prompt → 大模型 → JSON 结果
