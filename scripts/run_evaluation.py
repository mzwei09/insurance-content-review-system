#!/usr/bin/env python3
"""运行评估脚本 - 加载测试集、调用审核、生成报告"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _load_test_cases() -> list[dict]:
    path = ROOT / "data" / "test_cases" / "test_cases.json"
    if not path.exists():
        raise FileNotFoundError(f"测试用例文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_reviewer():
    """初始化 ContentReviewer，优先使用向量库"""
    from src.reviewer import ContentReviewer
    from src.retriever import Retriever
    from src.vectorstore import VectorStore

    import yaml
    config_path = ROOT / "config.yaml"
    cfg = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    vs_cfg = cfg.get("vectorstore", {})
    ret_cfg = cfg.get("retriever", {})
    index_path = vs_cfg.get("index_path", "data/vectorstore/faiss.index")
    metadata_path = vs_cfg.get("metadata_path", "data/vectorstore/metadata.json")
    if not Path(index_path).is_absolute():
        index_path = str(ROOT / index_path)
    if not Path(metadata_path).is_absolute():
        metadata_path = str(ROOT / metadata_path)

    vectorstore = None
    if Path(index_path).exists():
        vectorstore = VectorStore(
            dimension=vs_cfg.get("dimension", 1536),
            index_path=index_path,
            metadata_path=metadata_path,
        )
        if not vectorstore.load():
            vectorstore = None

    retriever = Retriever(vectorstore, **ret_cfg) if vectorstore else None
    return ContentReviewer(vectorstore=vectorstore, retriever=retriever, config=cfg)


def _generate_html_report(result: dict, output_path: Path) -> None:
    """生成 HTML 报告"""
    s = result["summary"]
    metrics = result.get("metrics_by_violation_type", {})
    cm = result.get("confusion_matrix", {})
    errors = result.get("error_cases", [])

    def _metric_class(v: float) -> str:
        if v >= 0.8:
            return "metric-good"
        if v >= 0.6:
            return "metric-warn"
        return "metric-bad"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>审核系统评估报告</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
    .container {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    h1 {{ margin-top: 0; color: #333; border-bottom: 2px solid #4a90d9; padding-bottom: 8px; }}
    h2 {{ color: #555; margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 10px 12px; text-align: left; }}
    th {{ background: #4a90d9; color: #fff; font-weight: 600; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    tr:hover {{ background: #f0f7ff; }}
    .metric-good {{ color: #28a745; font-weight: 600; }}
    .metric-warn {{ color: #ffc107; font-weight: 600; }}
    .metric-bad {{ color: #dc3545; font-weight: 600; }}
    .error-row {{ background: #ffe6e6 !important; }}
    .error-row:hover {{ background: #ffd6d6 !important; }}
    .confusion-matrix {{ margin: 16px 0; }}
    .confusion-matrix th {{ background: #555; }}
    .section {{ margin-bottom: 32px; }}
    pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 13px; }}
    .no-errors {{ color: #28a745; font-weight: 500; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>保险营销内容审核系统 - 评估报告</h1>

    <section class="section">
      <h2>1. 总体指标</h2>
      <table>
        <thead>
          <tr><th>指标</th><th>数值</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr><td>测试用例总数</td><td>{s['total_cases']}</td><td>-</td></tr>
          <tr><td>合规判断正确数</td><td>{s['correct_compliance']}</td><td>-</td></tr>
          <tr><td>准确率 (Accuracy)</td><td class="{_metric_class(s['accuracy'])}">{s['accuracy']:.2%}</td><td>(TP+TN)/总数</td></tr>
          <tr><td>宏平均精确率</td><td class="{_metric_class(s['macro_precision'])}">{s['macro_precision']:.2%}</td><td>-</td></tr>
          <tr><td>宏平均召回率</td><td class="{_metric_class(s['macro_recall'])}">{s['macro_recall']:.2%}</td><td>-</td></tr>
          <tr><td>宏平均 F1</td><td class="{_metric_class(s['macro_f1'])}">{s['macro_f1']:.2%}</td><td>-</td></tr>
          <tr><td>条文引用准确率</td><td class="{_metric_class(s['article_citation_accuracy'])}">{s['article_citation_accuracy']:.2%}</td><td>正确引用数/总引用数 ({s['correct_citations']}/{s['total_citations']})</td></tr>
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>2. 各违规类型指标</h2>
      <table>
        <thead>
          <tr><th>违规类型</th><th>精确率</th><th>召回率</th><th>F1</th><th>TP</th><th>FP</th><th>FN</th></tr>
        </thead>
        <tbody>
"""
    for vt, m in metrics.items():
        html += f"""          <tr>
            <td>{vt}</td>
            <td class="{_metric_class(m['precision'])}">{m['precision']:.2%}</td>
            <td class="{_metric_class(m['recall'])}">{m['recall']:.2%}</td>
            <td class="{_metric_class(m['f1'])}">{m['f1']:.2%}</td>
            <td>{m['tp']}</td>
            <td>{m['fp']}</td>
            <td>{m['fn']}</td>
          </tr>
"""
    html += """        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>3. 混淆矩阵</h2>
      <p>行=实际类别，列=预测类别</p>
      <table class="confusion-matrix">
        <thead>
          <tr><th>实际 \\ 预测</th>
"""
    all_pred = set()
    for row in cm.values():
        all_pred.update(row.keys())
    pred_cols = sorted(all_pred)
    for col in pred_cols:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for actual in sorted(cm.keys()):
        html += f"<tr><th>{actual}</th>"
        for col in pred_cols:
            html += f"<td>{cm.get(actual, {}).get(col, 0)}</td>"
        html += "</tr>"
    html += """        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>4. 条文引用准确率说明</h2>
      <p>正确引用数：模型引用的条文编号在 expected_articles 中的数量。</p>
      <p>总引用数：模型引用的所有条文数量。</p>
    </section>

    <section class="section">
      <h2>5. 错误案例 ("""
    html += str(len(errors)) + """)</h2>
"""
    if not errors:
        html += '      <p class="no-errors">无错误案例，全部预测正确。</p>'
    else:
        html += """      <table>
        <thead>
          <tr><th>ID</th><th>内容摘要</th><th>预期</th><th>预测</th><th>预期条文</th><th>预测条文</th><th>说明</th></tr>
        </thead>
        <tbody>
"""
        for e in errors:
            exp = "合规" if e["expected_compliance"] else f"违规({e['expected_violation_type']})"
            pred = "合规" if e["predicted_compliance"] else f"违规({e['predicted_violation_type']})"
            html += f"""          <tr class="error-row">
            <td>{e['id']}</td>
            <td>{e['content']}</td>
            <td>{exp}</td>
            <td>{pred}</td>
            <td>{', '.join(e.get('expected_articles') or [])}</td>
            <td>{', '.join(e.get('predicted_articles') or [])}</td>
            <td>{e.get('description', '')}</td>
          </tr>
"""
        html += """        </tbody>
      </table>
"""
    html += """    </section>
  </div>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _generate_md_report(result: dict, output_path: Path) -> None:
    """生成 Markdown 报告"""
    s = result["summary"]
    metrics = result.get("metrics_by_violation_type", {})
    cm = result.get("confusion_matrix", {})
    errors = result.get("error_cases", [])

    lines = [
        "# 保险营销内容审核系统 - 评估报告",
        "",
        "## 1. 总体指标",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 测试用例总数 | {s['total_cases']} |",
        f"| 合规判断正确数 | {s['correct_compliance']} |",
        f"| 准确率 (Accuracy) | {s['accuracy']:.2%} |",
        f"| 宏平均精确率 | {s['macro_precision']:.2%} |",
        f"| 宏平均召回率 | {s['macro_recall']:.2%} |",
        f"| 宏平均 F1 | {s['macro_f1']:.2%} |",
        f"| 条文引用准确率 | {s['article_citation_accuracy']:.2%} ({s['correct_citations']}/{s['total_citations']}) |",
        "",
        "## 2. 各违规类型指标",
        "",
        "| 违规类型 | 精确率 | 召回率 | F1 | TP | FP | FN |",
        "|----------|--------|--------|-----|----|----|-----|",
    ]
    for vt, m in metrics.items():
        lines.append(f"| {vt} | {m['precision']:.2%} | {m['recall']:.2%} | {m['f1']:.2%} | {m['tp']} | {m['fp']} | {m['fn']} |")
    lines.extend(["", "## 3. 混淆矩阵", "", "行=实际类别，列=预测类别", ""])

    all_pred = set()
    for row in cm.values():
        all_pred.update(row.keys())
    pred_cols = sorted(all_pred)
    header = "| 实际 \\ 预测 | " + " | ".join(pred_cols) + " |"
    sep = "|" + "---|" * (len(pred_cols) + 1)
    lines.append(header)
    lines.append(sep)
    for actual in sorted(cm.keys()):
        row_vals = [str(cm.get(actual, {}).get(col, 0)) for col in pred_cols]
        lines.append("| " + actual + " | " + " | ".join(row_vals) + " |")
    lines.extend(["", "## 4. 错误案例", ""])
    if not errors:
        lines.append("无错误案例，全部预测正确。")
    else:
        lines.append("| ID | 内容摘要 | 预期 | 预测 | 预期条文 | 预测条文 | 说明 |")
        lines.append("|----|----------|------|------|----------|----------|------|")
        for e in errors:
            exp = "合规" if e["expected_compliance"] else f"违规({e['expected_violation_type']})"
            pred = "合规" if e["predicted_compliance"] else f"违规({e['predicted_violation_type']})"
            exp_arts = ", ".join(e.get("expected_articles") or [])
            pred_arts = ", ".join(e.get("predicted_articles") or [])
            desc = (e.get("description", "") or "").replace("|", "\\|")
            content = (e.get("content", "") or "")[:50].replace("|", "\\|")
            lines.append(f"| {e['id']} | {content}... | {exp} | {pred} | {exp_arts} | {pred_arts} | {desc} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("=" * 60)
    print("保险营销内容审核系统 - 评估脚本")
    print("=" * 60)

    test_cases = _load_test_cases()
    print(f"\n加载测试用例: {len(test_cases)} 条")

    print("初始化审核器...")
    reviewer = _get_reviewer()

    print("开始逐条审核...")
    predictions = []
    for i, tc in enumerate(test_cases):
        content = tc.get("content", "")
        pred = reviewer.review(content)
        predictions.append(pred)
        status = "✓" if pred.get("compliance") else "✗"
        print(f"  [{i+1}/{len(test_cases)}] {tc.get('id', '')} {status}")

    print("\n计算评估指标...")
    from src.evaluator import Evaluator
    evaluator = Evaluator()
    result = evaluator.evaluate(test_cases, predictions)

    s = result["summary"]
    print("\n" + "=" * 60)
    print("关键指标")
    print("=" * 60)
    print(f"  准确率 (Accuracy):        {s['accuracy']:.2%}")
    print(f"  宏平均精确率:             {s['macro_precision']:.2%}")
    print(f"  宏平均召回率:             {s['macro_recall']:.2%}")
    print(f"  宏平均 F1:                {s['macro_f1']:.2%}")
    print(f"  条文引用准确率:           {s['article_citation_accuracy']:.2%} ({s['correct_citations']}/{s['total_citations']})")
    print(f"  错误案例数:               {result['error_count']}")
    print("=" * 60)

    reports_dir = ROOT / "reports"
    html_path = reports_dir / "evaluation_report.html"
    md_path = reports_dir / "evaluation_report.md"
    _generate_html_report(result, html_path)
    _generate_md_report(result, md_path)
    print(f"\n报告已生成:")
    print(f"  HTML: {html_path}")
    print(f"  MD:   {md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
