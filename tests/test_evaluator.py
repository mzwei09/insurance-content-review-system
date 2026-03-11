"""评估模块单元测试"""

import pytest
from src.evaluator import Evaluator


def test_evaluator_accuracy():
    """测试准确率计算"""
    evaluator = Evaluator()
    test_cases = [
        {"id": "1", "content": "合规", "expected_compliance": True, "expected_violation_type": None, "expected_articles": []},
        {"id": "2", "content": "违规", "expected_compliance": False, "expected_violation_type": "夸大收益", "expected_articles": ["第二十三条"]},
    ]
    predictions = [
        {"compliance": True, "violation_type": None, "cited_articles": []},
        {"compliance": False, "violation_type": "夸大收益", "cited_articles": [{"article_id": "第二十三条", "article_text": "...", "relevance_score": 0.9}]},
    ]
    result = evaluator.evaluate(test_cases, predictions)
    assert result["summary"]["accuracy"] == 1.0
    assert result["summary"]["correct_compliance"] == 2
    assert result["error_count"] == 0


def test_evaluator_error_cases():
    """测试错误案例记录"""
    evaluator = Evaluator()
    test_cases = [
        {"id": "1", "content": "合规内容", "expected_compliance": True, "expected_violation_type": None, "expected_articles": []},
    ]
    predictions = [
        {"compliance": False, "violation_type": "夸大收益", "cited_articles": []},
    ]
    result = evaluator.evaluate(test_cases, predictions)
    assert result["error_count"] == 1
    assert len(result["error_cases"]) == 1
    assert result["error_cases"][0]["expected_compliance"] is True
    assert result["error_cases"][0]["predicted_compliance"] is False


def test_evaluator_article_citation():
    """测试条文引用准确率"""
    evaluator = Evaluator()
    test_cases = [
        {"id": "1", "content": "违规", "expected_compliance": False, "expected_violation_type": "夸大收益", "expected_articles": ["第二十三条"]},
    ]
    predictions = [
        {"compliance": False, "violation_type": "夸大收益", "cited_articles": [
            {"article_id": "第二十三条", "article_text": "...", "relevance_score": 0.9},
            {"article_id": "第十五条", "article_text": "...", "relevance_score": 0.8},
        ]},
    ]
    result = evaluator.evaluate(test_cases, predictions)
    # 第二十三条在 expected 中，第十五条不在
    assert result["summary"]["total_citations"] == 2
    assert result["summary"]["correct_citations"] >= 1
    assert result["summary"]["article_citation_accuracy"] > 0


def test_evaluator_length_mismatch():
    """测试 test_cases 与 predictions 数量不一致"""
    evaluator = Evaluator()
    test_cases = [{"id": "1", "content": "x", "expected_compliance": True, "expected_violation_type": None, "expected_articles": []}]
    predictions = []
    with pytest.raises(ValueError, match="数量不一致"):
        evaluator.evaluate(test_cases, predictions)
