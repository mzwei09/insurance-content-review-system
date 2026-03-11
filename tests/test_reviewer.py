"""审核模块单元测试 - 使用 mock 避免真实 API 调用"""

import pytest
from unittest.mock import patch, MagicMock


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_compliant(mock_call_llm):
    """测试合规内容的审核"""
    from src.reviewer import ContentReviewer

    mock_call_llm.return_value = {
        "compliance": True,
        "violation_type": None,
        "cited_articles": [],
        "confidence": 0.92,
        "reasoning": "内容未发现违规表述，符合监管要求。",
    }
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("这是一款保障全面的重疾险产品，请根据自身需求选择。")

    assert result["compliance"] is True
    assert result["violation_type"] is None
    assert result["confidence"] >= 0.9
    assert "reasoning" in result
    mock_call_llm.assert_called_once()


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_violation(mock_call_llm):
    """测试违规内容的解析"""
    from src.reviewer import ContentReviewer

    mock_call_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "cited_articles": [
            {"article_id": "银保监发〔2021〕XX号", "article_text": "禁止承诺保本保息", "relevance_score": 0.92}
        ],
        "confidence": 0.95,
        "reasoning": "内容承诺保本保息，违反监管规定。",
    }
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("购买此产品保证年化收益 8%，保本保息")

    assert result["compliance"] is False
    assert result["violation_type"] == "夸大收益"
    assert len(result["cited_articles"]) > 0
    assert result["cited_articles"][0]["article_id"] == "银保监发〔2021〕XX号"
    mock_call_llm.assert_called_once()


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_empty_content(mock_call_llm):
    """测试空内容的边界情况"""
    from src.reviewer import ContentReviewer

    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("")
    result2 = reviewer.review("   ")

    assert result["compliance"] is True
    assert "内容为空" in result["reasoning"]
    assert result2["compliance"] is True
    mock_call_llm.assert_not_called()


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_with_retriever(mock_call_llm):
    """测试带检索器的审核流程"""
    from src.reviewer import ContentReviewer
    from src.retriever import Retriever

    mock_vectorstore = MagicMock()
    mock_vectorstore.search.return_value = [
        ({"article_id": "A1", "text": "禁止夸大收益", "article_text": "禁止夸大收益"}, 0.85),
        ({"article_id": "A2", "text": "禁止误导性陈述", "article_text": "禁止误导性陈述"}, 0.72),
    ]
    retriever = Retriever(mock_vectorstore, top_k=5, score_threshold=0.6)
    reviewer = ContentReviewer(vectorstore=mock_vectorstore, retriever=retriever)

    mock_call_llm.return_value = {
        "compliance": False,
        "violation_type": "夸大收益",
        "cited_articles": [{"article_id": "A1", "article_text": "禁止夸大收益", "relevance_score": 0.85}],
        "confidence": 0.9,
        "reasoning": "违反 A1 条文。",
    }
    result = reviewer.review("年化收益 10% 稳赚不赔")

    mock_vectorstore.search.assert_called_once_with("年化收益 10% 稳赚不赔", top_k=5, api_key=None)
    assert result["compliance"] is False
    mock_call_llm.assert_called_once()


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_json_parse_failure(mock_call_llm):
    """测试 LLM 返回非 JSON 时的兜底处理"""
    from src.reviewer import ContentReviewer

    mock_call_llm.side_effect = ValueError("Invalid JSON")
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("某营销内容")

    assert result["compliance"] is False
    assert "解析失败" in result["reasoning"] or "人工复核" in result["reasoning"]


@patch("src.reviewer.call_llm_json")
def test_content_reviewer_output_validation(mock_call_llm):
    """测试输出格式验证与补全"""
    from src.reviewer import ContentReviewer

    mock_call_llm.return_value = {
        "compliance": True,
        "violation_type": None,
        "cited_articles": [{"article_id": "X", "article_text": "某条文"}],
        "confidence": 0.88,
        "reasoning": "合规",
    }
    reviewer = ContentReviewer(vectorstore=None, retriever=None)
    result = reviewer.review("合规文案")

    assert "relevance_score" in result["cited_articles"][0]
    assert 0 <= result["confidence"] <= 1


def test_retriever_filters_low_score():
    """测试检索器过滤低相似度结果"""
    from src.retriever import Retriever

    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        ({"article_id": "A1", "text": "条文1"}, 0.9),
        ({"article_id": "A2", "text": "条文2"}, 0.5),
        ({"article_id": "A3", "text": "条文3"}, 0.65),
    ]
    retriever = Retriever(mock_vs, top_k=5, score_threshold=0.6)
    articles = retriever.retrieve("查询")

    assert len(articles) == 2
    assert all(a["relevance_score"] >= 0.6 for a in articles)
    assert articles[0]["article_id"] == "A1"
    assert articles[0]["article_text"] == "条文1"


def test_retriever_metadata_flexibility():
    """测试检索器对元数据字段的兼容性"""
    from src.retriever import Retriever

    mock_vs = MagicMock()
    mock_vs.search.return_value = [
        ({"id": "doc_1", "article_text": "内容A"}, 0.8),
        ({"article_id": "doc_2", "text": "内容B"}, 0.75),
    ]
    retriever = Retriever(mock_vs, score_threshold=0.6)
    articles = retriever.retrieve("q")

    assert articles[0]["article_id"] in ("doc_1", "doc_2")
    assert len(articles[0]["article_text"]) > 0
