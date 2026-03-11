"""多模态审核模块单元测试 - 使用 mock 避免真实 API 调用"""

import base64
from unittest.mock import patch, MagicMock

import pytest

# 1x1 红色 PNG 的 base64
MINI_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="


@patch("src.reviewer.call_llm_json")
def test_multimodal_reviewer_text_only(mock_llm):
    """测试多模态审核 - 仅文本，无图片"""
    from src.multimodal_reviewer import MultimodalReviewer

    mock_llm.return_value = {
        "compliance": True,
        "violation_type": None,
        "violation_types": None,
        "cited_articles": [],
        "confidence": 0.9,
        "reasoning": "合规",
    }
    reviewer = MultimodalReviewer(vectorstore=None, retriever=None)
    with patch("src.multimodal_reviewer._extract_text_from_images") as mock_extract:
        result = reviewer.review("本产品为保障型重疾险。", image_urls=None, api_key="sk-test")
    assert result["compliance"] is True
    mock_extract.assert_not_called()


@patch("src.multimodal_reviewer._extract_text_from_images")
@patch("src.reviewer.call_llm_json")
def test_multimodal_reviewer_with_images(mock_llm, mock_extract):
    """测试多模态审核 - 文本 + 图片"""
    from src.multimodal_reviewer import MultimodalReviewer

    mock_extract.return_value = "【图片1】投保即返现，收益高达15%！"
    mock_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "violation_types": ["夸大收益"],
        "cited_articles": [{"article_id": "第二十三条", "article_text": "...", "relevance_score": 0.9}],
        "confidence": 0.95,
        "reasoning": "承诺收益违规",
    }
    reviewer = MultimodalReviewer(vectorstore=None, retriever=None)
    result = reviewer.review(
        content="查看图片",
        image_urls=["data:image/png;base64," + MINI_PNG_B64],
        api_key="sk-test",
    )
    assert result["compliance"] is False
    assert "夸大收益" in (result.get("violation_type") or "") or "夸大收益" in str(result.get("violation_types") or [])
    mock_extract.assert_called()


@patch("src.multimodal_reviewer._extract_text_from_images")
def test_multimodal_reviewer_image_extraction_failure(mock_extract):
    """测试多模态审核 - 图片提取失败"""
    from src.multimodal_reviewer import MultimodalReviewer

    mock_extract.side_effect = ValueError("图片无效")
    reviewer = MultimodalReviewer(vectorstore=None, retriever=None)
    result = reviewer.review(
        content="",
        image_urls=["data:image/png;base64,invalid"],
        api_key="sk-test",
        detailed=False,
    )
    assert result["compliance"] is False
    assert "失败" in result.get("reasoning", "") or "图片" in result.get("reasoning", "")


@patch("src.multimodal_reviewer._extract_text_from_images")
@patch("src.reviewer.call_llm_json")
def test_multimodal_reviewer_detailed_mode(mock_llm, mock_extract):
    """测试多模态审核 - 详细模式（分别审核文本和每张图片）"""
    from src.multimodal_reviewer import MultimodalReviewer

    def extract_side_effect(urls, *args, **kwargs):
        return "【图片1】稳赚不赔，年化10%！" if urls else ""

    mock_extract.side_effect = extract_side_effect
    mock_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "violation_types": ["夸大收益"],
        "cited_articles": [],
        "confidence": 0.9,
        "reasoning": "违规",
    }
    reviewer = MultimodalReviewer(vectorstore=None, retriever=None)
    result = reviewer.review(
        content="合规的文本介绍",
        image_urls=["data:image/png;base64," + MINI_PNG_B64],
        api_key="sk-test",
        detailed=True,
    )
    assert "text_result" in result or "image_results" in result
    assert result.get("compliance") is False  # 图片违规导致整体违规


def test_parse_batch_extraction_output():
    """测试批量图片提取输出的解析"""
    from src.multimodal_reviewer import _parse_batch_extraction_output

    text = "【图片1】第一张图的内容\n\n【图片2】第二张图的内容"
    result = _parse_batch_extraction_output(text, 2)
    assert len(result) == 2
    assert "第一张图" in result[0]
    assert "第二张图" in result[1]


def test_parse_batch_extraction_empty():
    """测试空输出的解析"""
    from src.multimodal_reviewer import _parse_batch_extraction_output

    result = _parse_batch_extraction_output("", 3)
    assert len(result) == 3
    assert all(s == "" for s in result)


def test_parse_batch_extraction_fallback():
    """测试解析失败时的兜底（整段作为第一张图）"""
    from src.multimodal_reviewer import _parse_batch_extraction_output

    text = "没有标准格式的文本"
    result = _parse_batch_extraction_output(text, 1)
    assert len(result) == 1
    assert result[0] == "没有标准格式的文本"


@patch("src.multimodal_reviewer._extract_text_from_images")
@patch("src.reviewer.call_llm_json")
def test_multimodal_reviewer_images_only_no_text(mock_llm, mock_extract):
    """测试多模态审核 - 仅图片无文本"""
    from src.multimodal_reviewer import MultimodalReviewer

    mock_extract.return_value = "【图片1】投保即返现，收益15%！"
    mock_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "violation_types": ["夸大收益"],
        "cited_articles": [],
        "confidence": 0.9,
        "reasoning": "图片内容违规",
    }
    reviewer = MultimodalReviewer(vectorstore=None, retriever=None)
    result = reviewer.review(
        content="",
        image_urls=["data:image/png;base64," + MINI_PNG_B64],
        api_key="sk-test",
    )
    assert result["compliance"] is False
    mock_extract.assert_called()
