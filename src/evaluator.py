"""评估模块 - 测试数据集效果评估与指标计算"""

import re
from collections import defaultdict
from typing import Any


def _normalize_article_id(article_id: str) -> str:
    """标准化条文编号，提取'第X条'等关键部分便于匹配"""
    if not article_id or not isinstance(article_id, str):
        return ""
    s = str(article_id).strip()
    # 提取 "第X条" 模式
    match = re.search(r"第[一二三四五六七八九十百千零〇\d]+条", s)
    if match:
        return match.group(0)
    # 若无此模式，返回原字符串（用于银保监发等格式）
    return s


def _article_match(cited_id: str, expected_list: list[str]) -> bool:
    """判断引用的条文是否在预期列表中（支持模糊匹配）"""
    if not expected_list:
        return False
    norm_cited = _normalize_article_id(cited_id)
    if not norm_cited:
        return cited_id in expected_list
    for exp in expected_list:
        norm_exp = _normalize_article_id(exp)
        if norm_exp and (norm_cited == norm_exp or norm_exp in norm_cited or norm_cited in norm_exp):
            return True
        if cited_id in exp or exp in cited_id:
            return True
    return False


class Evaluator:
    """审核效果评估器"""

    def evaluate(self, test_cases: list[dict], predictions: list[dict]) -> dict:
        """
        评估审核结果。

        Args:
            test_cases: 测试用例列表，每项含 id, content, expected_compliance,
                        expected_violation_type, expected_articles, description
            predictions: 预测结果列表，与 test_cases 一一对应，每项含 compliance,
                         violation_type, cited_articles, confidence, reasoning

        Returns:
            完整评估结果字典
        """
        if len(test_cases) != len(predictions):
            raise ValueError(
                f"test_cases 与 predictions 数量不一致: {len(test_cases)} vs {len(predictions)}"
            )

        # 1. 准确率 (Accuracy)
        correct_compliance = 0
        total = len(test_cases)

        # 2. 按违规类型的 TP, FP, FN
        violation_types = set()
        for tc in test_cases:
            vt = tc.get("expected_violation_type")
            if vt:
                violation_types.add(vt)

        tp_by_type: dict[str, int] = defaultdict(int)
        fp_by_type: dict[str, int] = defaultdict(int)
        fn_by_type: dict[str, int] = defaultdict(int)

        # 3. 条文引用统计
        total_citations = 0
        correct_citations = 0

        # 4. 错误案例
        error_cases: list[dict] = []
        # 5. 混淆矩阵: 行=实际, 列=预测
        confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for tc, pred in zip(test_cases, predictions):
            case_id = tc.get("id", "")
            expected_compliance = tc.get("expected_compliance", True)
            expected_violation = tc.get("expected_violation_type") or ""
            expected_articles = tc.get("expected_articles") or []

            pred_compliance = pred.get("compliance", True)
            pred_violation = (pred.get("violation_type") or "").strip()
            cited = pred.get("cited_articles") or []

            # 合规判断
            if expected_compliance == pred_compliance:
                correct_compliance += 1
            else:
                error_cases.append({
                    "id": case_id,
                    "content": tc.get("content", "")[:100] + ("..." if len(tc.get("content", "")) > 100 else ""),
                    "expected_compliance": expected_compliance,
                    "expected_violation_type": expected_violation or None,
                    "expected_articles": expected_articles,
                    "predicted_compliance": pred_compliance,
                    "predicted_violation_type": pred_violation or None,
                    "predicted_articles": [c.get("article_id", "") for c in cited],
                    "reasoning": pred.get("reasoning", ""),
                    "description": tc.get("description", ""),
                })

            # 混淆矩阵键
            actual_key = "合规" if expected_compliance else (expected_violation or "违规")
            pred_key = "合规" if pred_compliance else (pred_violation or "违规")
            confusion[actual_key][pred_key] += 1

            # 按违规类型的 TP/FP/FN
            if expected_compliance:
                # 实际合规：预测违规则为 FP
                if not pred_compliance and pred_violation:
                    fp_by_type[pred_violation] += 1
            else:
                # 实际违规
                if pred_compliance:
                    fn_by_type[expected_violation] += 1
                else:
                    if pred_violation == expected_violation:
                        tp_by_type[expected_violation] += 1
                    else:
                        fp_by_type[pred_violation] += 1
                        fn_by_type[expected_violation] += 1

            # 条文引用
            for c in cited:
                aid = c.get("article_id", "")
                if not aid:
                    continue
                total_citations += 1
                if _article_match(aid, expected_articles):
                    correct_citations += 1
                # 合规案例下，引用任何条文都可视为不准确（预期无引用）
                elif expected_compliance:
                    pass  # 不计入 correct
                # 违规案例下，未在 expected 中则不计入 correct

        accuracy = correct_compliance / total if total else 0.0

        # 按类型计算精确率、召回率、F1
        metrics_by_type: dict[str, dict[str, float]] = {}
        for vt in sorted(violation_types):
            tp = tp_by_type[vt]
            fp = fp_by_type[vt]
            fn = fn_by_type[vt]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            metrics_by_type[vt] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

        # 宏平均
        if metrics_by_type:
            avg_precision = sum(m["precision"] for m in metrics_by_type.values()) / len(metrics_by_type)
            avg_recall = sum(m["recall"] for m in metrics_by_type.values()) / len(metrics_by_type)
            macro_f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0.0
        else:
            avg_precision = avg_recall = macro_f1 = 0.0

        article_accuracy = correct_citations / total_citations if total_citations > 0 else 0.0

        return {
            "summary": {
                "total_cases": total,
                "correct_compliance": correct_compliance,
                "accuracy": round(accuracy, 4),
                "macro_precision": round(avg_precision, 4),
                "macro_recall": round(avg_recall, 4),
                "macro_f1": round(macro_f1, 4),
                "article_citation_accuracy": round(article_accuracy, 4),
                "total_citations": total_citations,
                "correct_citations": correct_citations,
            },
            "metrics_by_violation_type": metrics_by_type,
            "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
            "error_cases": error_cases,
            "error_count": len(error_cases),
        }
