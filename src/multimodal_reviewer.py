"""多模态审核模块 - 支持图文混合内容的合规审核"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Union

from .reviewer import ContentReviewer


def _extract_text_from_images(
    image_urls: List[str],
    model: str = "qwen-vl-max",
    api_key: Optional[str] = None,
) -> str:
    """
    使用 qwen-vl-max 从多张图片中提取文字内容。

    Args:
        image_urls: 图片 URL 列表（支持 data URL 或公网 URL）
        model: 多模态模型名称
        api_key: API 密钥，为 None 时从环境变量读取

    Returns:
        所有图片中的文字描述（合并）
    """
    if not image_urls:
        return ""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("多模态审核需要安装 openai: pip install openai")

    import os
    key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise ValueError("请配置 DASHSCOPE_API_KEY")

    client = OpenAI(
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    # 构建 content：多张图片 + 提示文本
    content = []
    for url in image_urls:
        if url and url.strip():
            content.append({"type": "image_url", "image_url": {"url": url.strip()}})
    if not content:
        return ""
    content.append({
        "type": "text",
        "text": "请完整提取并描述每张图片中的所有文字内容，包括标题、正文、标语等。若为营销海报，请逐条列出所有可见文案。多张图片请按顺序分别描述，用【图片1】【图片2】等区分。",
    })

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
    )
    return resp.choices[0].message.content or ""


def _parse_batch_extraction_output(text: str, num_images: int) -> List[str]:
    """
    解析批量图片提取输出，按【图片1】【图片2】等分隔为每张图片的文本。

    Args:
        text: 批量提取的原始输出
        num_images: 图片数量

    Returns:
        每张图片对应的文本列表，顺序与 image_urls 一致
    """
    if not text or not text.strip():
        return [""] * num_images
    parts = re.split(r"【图片(\d+)】", text)
    result = [""] * num_images
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            try:
                idx = int(parts[i])
                content = parts[i + 1].strip()
                if 1 <= idx <= num_images:
                    result[idx - 1] = content
            except (ValueError, IndexError):
                continue
    # 解析失败时，将整个文本作为第一张图片内容（兜底）
    if num_images >= 1 and not any(s.strip() for s in result):
        result[0] = text.strip()
    return result


class MultimodalReviewer(ContentReviewer):
    """
    多模态审核器 - 继承 ContentReviewer，支持图文混合内容。

    流程：
    1. 若有图片 URL，使用 qwen-vl-max 提取图片中的文字
    2. 将文本内容与图片文字合并
    3. 调用父类 ContentReviewer.review() 进行合规审核
    """

    def __init__(
        self,
        multimodal_model: str = "qwen-vl-max",
        **kwargs,
    ):
        """
        Args:
            multimodal_model: 多模态模型名称，用于图片文字提取
            **kwargs: 传递给 ContentReviewer 的参数
        """
        super().__init__(**kwargs)
        self.multimodal_model = multimodal_model

    def review(
        self,
        content: str,
        image_url: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        detailed: bool = True,  # 新增：是否返回每张图片的详细结果
    ) -> dict:
        """
        审核营销内容（支持纯文本或图文混合）。

        Args:
            content: 待审核的文本内容
            image_url: 可选，单张配图 URL（与 image_urls 二选一）
            image_urls: 可选，多张配图 URL 列表
            api_key: 百炼 API 密钥，用于图片提取和父类审核
            detailed: 是否返回每张图片的详细审核结果（默认True）

        Returns:
            {
                "compliance": bool,
                "violation_types": list[str] or None,
                "cited_articles": list,
                "confidence": float,
                "reasoning": str,
                "text_result": dict,  # 纯文本的审核结果（如果有文本）
                "image_results": list[dict],  # 每张图片的审核结果
            }
        """
        text_content = (content or "").strip()
        urls = []
        if image_urls:
            urls = [u for u in image_urls if u and str(u).strip()]
        if not urls and image_url and image_url.strip():
            urls = [image_url.strip()]

        cfg_api_key = self.config.get("api", {}).get("dashscope_api_key") if self.config else None
        key = api_key or cfg_api_key

        # 如果开启详细模式，逐张审核图片
        if detailed and urls:
            return self._review_detailed(text_content, urls, key)
        
        # 否则使用原来的合并审核方式
        image_text = ""
        if urls:
            try:
                image_text = _extract_text_from_images(
                    urls,
                    model=self.multimodal_model,
                    api_key=key,
                )
            except Exception as e:
                return self._fallback_result(
                    f"图片文字提取失败：{e}，请检查图片是否有效或稍后重试。"
                )

        if image_text:
            combined = f"{text_content}\n\n【图片中的文字内容】\n{image_text}".strip()
        else:
            combined = text_content or ""

        if not combined:
            return self._fallback_result("文本和图片均无有效内容，无法审核。")

        return super().review(combined, api_key=api_key)

    def _review_detailed(self, text_content: str, image_urls: List[str], api_key: str) -> dict:
        """
        详细审核模式：分别审核文本和每张图片
        
        Returns:
            {
                "compliance": bool,  # 整体合规状态（任一违规则为False）
                "violation_types": list[str],  # 所有违规类型的合集
                "cited_articles": list,  # 所有引用条文的合集
                "confidence": float,  # 平均置信度
                "reasoning": str,  # 综合理由
                "text_result": dict or None,  # 文本审核结果
                "image_results": list[dict],  # 每张图片的审核结果
            }
        """
        text_result = None
        image_results = []
        
        # 1. 审核纯文本（如果有）
        if text_content:
            try:
                text_result = super().review(text_content, api_key=api_key)
                text_result["source"] = "文本内容"
            except Exception as e:
                text_result = {
                    "compliance": True,
                    "violation_types": None,
                    "reasoning": f"文本审核失败：{e}",
                    "source": "文本内容",
                }
        
        # 2. 逐张审核图片
        for idx, img_url in enumerate(image_urls, 1):
            try:
                # 提取单张图片的文字
                img_text = _extract_text_from_images(
                    [img_url],
                    model=self.multimodal_model,
                    api_key=api_key,
                )
                
                if not img_text or not img_text.strip():
                    image_results.append({
                        "image_index": idx,
                        "compliance": True,
                        "violation_types": None,
                        "reasoning": "图片无文字内容或提取失败",
                        "source": f"图片{idx}",
                    })
                    continue
                
                # 审核图片文字
                img_result = super().review(img_text, api_key=api_key)
                img_result["image_index"] = idx
                img_result["source"] = f"图片{idx}"
                img_result["extracted_text"] = img_text[:200]  # 保留前200字符
                image_results.append(img_result)
                
            except Exception as e:
                image_results.append({
                    "image_index": idx,
                    "compliance": True,
                    "violation_types": None,
                    "reasoning": f"图片审核失败：{e}",
                    "source": f"图片{idx}",
                })
        
        # 3. 汇总结果
        all_results = []
        if text_result:
            all_results.append(text_result)
        all_results.extend(image_results)
        
        # 计算整体合规状态（任一违规则整体违规）
        overall_compliance = all(r.get("compliance", True) for r in all_results)
        
        # 收集所有违规类型（去重）
        all_violation_types = []
        for r in all_results:
            vts = r.get("violation_types", [])
            if vts:
                for vt in vts:
                    if vt and vt not in all_violation_types:
                        all_violation_types.append(vt)
        
        # 收集所有引用条文（去重）
        all_cited_articles = []
        seen_article_ids = set()
        for r in all_results:
            for article in r.get("cited_articles", []):
                aid = article.get("article_id")
                if aid and aid not in seen_article_ids:
                    all_cited_articles.append(article)
                    seen_article_ids.add(aid)
        
        # 计算平均置信度
        confidences = [r.get("confidence", 0.5) for r in all_results if r.get("confidence")]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        
        # 生成综合理由
        reasoning_parts = []
        if text_result and not text_result.get("compliance"):
            reasoning_parts.append(f"【文本】{text_result.get('reasoning', '')}")
        
        for img_r in image_results:
            if not img_r.get("compliance"):
                idx = img_r.get("image_index", "?")
                reasoning_parts.append(f"【图片{idx}】{img_r.get('reasoning', '')}")
        
        combined_reasoning = "\n".join(reasoning_parts) if reasoning_parts else "所有内容均合规"
        
        return {
            "compliance": overall_compliance,
            "violation_types": all_violation_types if all_violation_types else None,
            "violation_type": all_violation_types[0] if all_violation_types else None,  # 向后兼容
            "cited_articles": all_cited_articles,
            "confidence": avg_confidence,
            "reasoning": combined_reasoning,
            "text_result": text_result,  # 文本审核详情
            "image_results": image_results,  # 每张图片审核详情
        }

    def _fallback_result(self, reasoning: str) -> dict:
        """返回解析失败时的兜底结果"""
        return {
            "compliance": False,
            "violation_type": None,
            "cited_articles": [],
            "confidence": 0.0,
            "reasoning": reasoning,
        }
