#!/usr/bin/env python3
"""构建监管文档知识库 - 解析文档、向量化并保存到 data/vectorstore/"""

import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.document_parser import parse_document
from src.vectorstore import VectorStore

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 默认监管文档列表（项目根目录或 data/documents）
DEFAULT_DOCS = [
    "保险销售行为管理办法.pdf",
    "金融产品网络营销管理办法（征求意见稿）.docx",
    "互联网保险业务监管办法.docx",
]


def _load_config() -> dict:
    """从 config.yaml 读取配置"""
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        logger.warning("未找到 config.yaml，使用默认配置")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def _resolve_doc_paths(doc_names: list[str]) -> list[Path]:
    """解析文档路径：优先项目根目录，其次 data/documents"""
    paths: list[Path] = []
    for name in doc_names:
        for base in [ROOT, ROOT / "data" / "documents"]:
            p = base / name
            if p.exists():
                paths.append(p)
                break
        else:
            logger.warning("未找到文档: %s", name)
    return paths


def main() -> int:
    cfg = _load_config()
    api_cfg = cfg.get("api", {})
    vs_cfg = cfg.get("vectorstore", {})

    api_key = api_cfg.get("dashscope_api_key") or os.getenv("DASHSCOPE_API_KEY") or ""
    embedding_model = (
        api_cfg.get("embedding_model") or vs_cfg.get("embedding_model") or "text-embedding-v2"
    )
    raw_path = vs_cfg.get("storage_path") or vs_cfg.get("index_path") or "data/vectorstore"
    if raw_path.endswith(".index") or raw_path.endswith(".json"):
        storage_path = str(ROOT / Path(raw_path).parent)
    else:
        storage_path = str(ROOT / raw_path) if not Path(raw_path).is_absolute() else raw_path

    dimension = vs_cfg.get("dimension", 1536)

    # 解析文档路径
    doc_paths = _resolve_doc_paths(DEFAULT_DOCS)
    if not doc_paths:
        logger.error(
            "未找到任何监管文档。请将以下文件放入项目根目录或 data/documents/：\n  - %s",
            "\n  - ".join(DEFAULT_DOCS),
        )
        return 1

    logger.info("待解析文档: %s", [p.name for p in doc_paths])

    # 解析条文
    all_articles: list[dict] = []
    for fp in doc_paths:
        try:
            articles = parse_document(str(fp))
            all_articles.extend(articles)
            logger.info("  %s: %d 条", fp.name, len(articles))
        except Exception as e:
            logger.exception("解析失败 %s: %s", fp, e)

    if not all_articles:
        logger.error("未解析到任何条文，请检查文档格式与内容")
        return 1

    logger.info("共解析 %d 条条文", len(all_articles))

    # 保存解析结果到 knowledge_base.json（无论向量化是否成功）
    kb_path = ROOT / "data" / "knowledge_base.json"
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    logger.info("已保存解析结果到 %s", kb_path)

    # 向量化并构建索引
    store = VectorStore(
        dimension=dimension,
        embedding_model=embedding_model,
        storage_path=storage_path,
        api_key=api_key or None,
        use_ip=True,
    )

    success, fail = store.add_articles(all_articles)
    if fail > 0:
        logger.warning("向量化失败 %d 条", fail)

    if success == 0:
        logger.error(
            "向量化全部失败。请配置 DASHSCOPE_API_KEY（config.yaml 的 api.dashscope_api_key 或环境变量）"
        )
        return 1

    store.save()

    # 统计信息
    print("\n" + "=" * 50)
    print("知识库构建完成")
    print("=" * 50)
    print(f"  解析文档数: {len(doc_paths)}")
    print(f"  解析条文数: {len(all_articles)}")
    print(f"  向量化成功: {success}")
    if fail > 0:
        print(f"  向量化失败: {fail}")
    print(f"  存储路径:   {storage_path}")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
