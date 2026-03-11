"""审核模块 - 基于 RAG 与大模型的营销内容合规审核"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .llm_client import call_llm_json
from .retriever import Retriever
from .vectorstore import VectorStore


def _load_config() -> dict:
    """加载 config.yaml"""
    path = Path(__file__).parent.parent / "config.yaml"
    if not path.exists():
        return {}
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_review_prompt() -> tuple[str, str]:
    """加载审核提示词，返回 (system_prompt, user_template)"""
    path = Path(__file__).parent.parent / "prompts" / "review_prompt.txt"
    if not path.exists():
        return _default_system_prompt(), _default_user_template()

    text = path.read_text(encoding="utf-8")
    parts = [p.strip() for p in text.split("=====")]
    system = ""
    user_template = ""
    few_shot_parts = []

    for i, p in enumerate(parts):
        if "SYSTEM PROMPT" in p:
            rest = p.split("SYSTEM PROMPT", 1)[-1].strip()
            system = rest if rest else (parts[i + 1] if i + 1 < len(parts) else "")
            break
    for i, p in enumerate(parts):
        if "USER PROMPT TEMPLATE" in p:
            rest = p.split("USER PROMPT TEMPLATE", 1)[-1].strip()
            user_template = rest if rest else (parts[i + 1] if i + 1 < len(parts) else "")
            break
    for i, p in enumerate(parts):
        if "FEW-SHOT EXAMPLE" in p and p.strip():
            # 包含示例标题及后续内容（直到下一个 ===== 分隔）
            combined = p.strip()
            if i + 1 < len(parts) and parts[i + 1].strip() and "FEW-SHOT EXAMPLE" not in parts[i + 1]:
                combined = combined + "\n" + parts[i + 1].strip()
            few_shot_parts.append(combined)

    if few_shot_parts and user_template:
        user_template = user_template + "\n\n【参考示例】\n" + "\n\n".join(few_shot_parts)

    if not system:
        system = _default_system_prompt()
    if not user_template:
        user_template = _default_user_template()
    return system, user_template


def _default_system_prompt() -> str:
    return """你是一位专业的保险营销内容合规审核专家。你的任务是根据监管条文判断营销内容是否合规。

审核原则：
1. 严格依据提供的监管条文进行判断
2. 必须引用具体条文编号和内容
3. 给出明确的违规类型和理由
4. 宁严勿松，存疑即标记为违规

输出格式：必须返回JSON格式。"""


def _default_user_template() -> str:
    return """请审核以下保险营销内容是否合规：

【待审核内容】
{content}

【相关监管条文】
{retrieved_articles}

【审核要求】
1. 判断内容是否违反任一条文
2. 如违规，指出所有违规类型（从以下类型中选择：夸大收益、无资质代言、误导性陈述、虚假宣传、未充分披露风险、违规承诺、不当比较）
3. 必须引用具体条文编号
4. 给出置信度（0-1之间）

【重要】如果内容包含多种违规行为，violation_types 应返回数组，包含所有违规类型。

请严格按照以下JSON格式输出：
{{
  "compliance": true/false,
  "violation_types": ["违规类型1", "违规类型2"] 或 null（合规时为null，违规时为数组，即使只有一种违规也用数组）,
  "cited_articles": [{{"article_id": "条文编号", "article_text": "条文内容", "relevance_score": 0.95}}],
  "confidence": 0.95,
  "reasoning": "判断理由，如有多种违规请分别说明"
}}"""


def _format_retrieved_articles(articles: list[dict]) -> str:
    """将检索到的条文格式化为 prompt 中的文本"""
    if not articles:
        return "（暂无检索到的监管条文，请基于通用保险营销合规常识判断）"
    lines = []
    for a in articles:
        aid = a.get("article_id", "")
        text = a.get("article_text", "")
        score = a.get("relevance_score", 0)
        lines.append(f"- 【{aid}】{text}（相似度：{score}）")
    return "\n".join(lines)


def _validate_review_output(data: dict) -> dict:
    """验证并补全审核输出格式"""
    required = {
        "compliance": True,
        "violation_types": None,  # 改为数组
        "cited_articles": [],
        "confidence": 0.5,
        "reasoning": "",
    }
    
    # 兼容旧格式：violation_type（单个）→ violation_types（数组）
    if "violation_type" in data and "violation_types" not in data:
        vt = data["violation_type"]
        data["violation_types"] = [vt] if vt else None
    
    out = {**required, **{k: v for k, v in data.items() if k in required}}

    if not isinstance(out["compliance"], bool):
        out["compliance"] = bool(out["compliance"])
    
    # 处理 violation_types：应为 None 或字符串数组
    if out["violation_types"] is not None:
        if isinstance(out["violation_types"], str):
            # 单个字符串转为数组
            out["violation_types"] = [out["violation_types"]]
        elif isinstance(out["violation_types"], list):
            # 确保数组中都是字符串
            out["violation_types"] = [str(v) for v in out["violation_types"] if v]
            if not out["violation_types"]:
                out["violation_types"] = None
        else:
            out["violation_types"] = None
    
    if not isinstance(out["cited_articles"], list):
        out["cited_articles"] = []
    for i, c in enumerate(out["cited_articles"]):
        if not isinstance(c, dict):
            out["cited_articles"][i] = {"article_id": "", "article_text": "", "relevance_score": 0.0}
        else:
            c.setdefault("article_id", "")
            c.setdefault("article_text", "")
            c.setdefault("relevance_score", 0.0)
    if not isinstance(out["confidence"], (int, float)):
        out["confidence"] = 0.5
    out["confidence"] = max(0.0, min(1.0, float(out["confidence"])))
    if not isinstance(out["reasoning"], str):
        out["reasoning"] = str(out["reasoning"])
    
    # 为了向后兼容，同时保留 violation_type（取第一个）
    out["violation_type"] = out["violation_types"][0] if out["violation_types"] else None
    
    return out


class ContentReviewer:
    """营销内容合规审核器 - 基于 RAG 检索 + 大模型推理"""

    def __init__(
        self,
        vectorstore: Optional[VectorStore] = None,
        retriever: Optional[Retriever] = None,
        model: str = "qwen-max",
        timeout: int = 30,
        max_retries: int = 3,
        confidence_threshold: Optional[float] = None,
        config: Optional[dict] = None,
    ):
        """
        Args:
            vectorstore: 向量库实例
            retriever: 检索器实例，若为 None 且 vectorstore 存在则自动创建
            model: 大模型名称
            timeout: API 超时（秒）
            max_retries: 最大重试次数
            confidence_threshold: 置信度阈值，低于此值建议人工复核
            config: 配置字典，为 None 时从 config.yaml 加载
        """
        self.config = config or _load_config()
        self.vectorstore = vectorstore
        if retriever is not None:
            self.retriever = retriever
        elif vectorstore is not None:
            ret_cfg = self.config.get("retriever", {})
            self.retriever = Retriever(vectorstore, **ret_cfg)
        else:
            self.retriever = None

        api_cfg = self.config.get("api", {})
        llm_cfg = self.config.get("llm", {})
        self.model = model or api_cfg.get("model_name") or llm_cfg.get("model", "qwen-max")
        self.timeout = timeout or llm_cfg.get("timeout", 30)
        self.max_retries = max_retries or llm_cfg.get("max_retries", 3)
        rev_cfg = self.config.get("review", {})
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else rev_cfg.get("confidence_threshold", 0.7)
        )

        self._system_prompt, self._user_template = _load_review_prompt()

    def review(self, content: str, api_key: str | None = None) -> dict:
        """
        审核营销内容是否合规。

        Args:
            content: 待审核的营销内容文本
            api_key: 百炼 API 密钥，若提供则优先使用（用户个人密钥）

        Returns:
            {
                "compliance": bool,
                "violation_types": list[str] or None,  # 多违规类型数组
                "violation_type": str or None,  # 向后兼容，取第一个违规类型
                "cited_articles": [{"article_id", "article_text", "relevance_score"}],
                "confidence": float,
                "reasoning": str
            }
        """
        import logging
        logger = logging.getLogger("aireview.reviewer")
        
        content = (content or "").strip()
        if not content:
            return _validate_review_output({
                "compliance": True,
                "violation_types": None,
                "cited_articles": [],
                "confidence": 0.0,
                "reasoning": "内容为空，无法审核",
            })

        logger.info("=" * 80)
        logger.info("🔍 开始审核流程")
        logger.info(f"📄 待审核内容: {content[:200]}{'...' if len(content) > 200 else ''}")
        logger.info("=" * 80)

        # a. 检索相关条文
        articles = []
        if self.retriever:
            logger.info("🔎 步骤1: 向量检索相关监管条文...")
            articles = self.retriever.retrieve(content, api_key=api_key)
            logger.info(f"✅ 检索到 {len(articles)} 条相关条文:")
            for i, art in enumerate(articles[:5], 1):  # 只打印前5条
                logger.info(f"  {i}. [{art.get('article_id', 'N/A')}] "
                          f"相似度: {art.get('relevance_score', 0):.3f} - "
                          f"{art.get('article_text', '')[:100]}...")
        else:
            logger.warning("⚠️  未配置向量检索器，将基于通用常识判断")

        retrieved_text = _format_retrieved_articles(articles)

        # b. 构造 prompt
        logger.info("-" * 80)
        logger.info("🔧 步骤2: 构造Prompt...")
        user_prompt = self._user_template.format(
            content=content,
            retrieved_articles=retrieved_text,
        )
        logger.info(f"✅ Prompt构造完成 (长度: {len(user_prompt)} 字符)")

        # c. 调用 LLM
        logger.info("-" * 80)
        logger.info("🤖 步骤3: 调用大模型进行推理...")
        try:
            data = call_llm_json(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                model=self.model,
                temperature=0.1,
                timeout=self.timeout,
                max_retries=self.max_retries,
                config=self.config,
                api_key=api_key,
            )
            logger.info("✅ 大模型推理完成")
            logger.info(f"📊 审核结果: 合规={data.get('compliance')}, "
                       f"违规类型={data.get('violation_types')}, "
                       f"置信度={data.get('confidence')}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ JSON解析失败: {e}")
            return _validate_review_output({
                "compliance": False,
                "violation_types": None,
                "cited_articles": [],
                "confidence": 0.0,
                "reasoning": f"模型输出解析失败，建议人工复核。错误：{e}",
            })
        except Exception as e:
            logger.error(f"❌ 审核异常: {e}")
            return _validate_review_output({
                "compliance": False,
                "violation_types": None,
                "cited_articles": [],
                "confidence": 0.0,
                "reasoning": f"审核服务异常：{e}，请稍后重试或人工复核。",
            })

        # d. 验证输出格式
        result = _validate_review_output(data)
        logger.info("=" * 80)
        logger.info("✅ 审核流程完成")
        logger.info("=" * 80)
        return result


# 兼容旧接口
Reviewer = ContentReviewer
