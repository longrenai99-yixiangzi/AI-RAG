from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.ingestion.atomic_evidence import ATOMIC_EXTENSIONS, build_atomic_evidence
from app.parsers import iter_source_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Markdown/XLSX atomic evidence in Shadow only.")
    parser.add_argument("--root", type=Path, default=Path(r"D:\设计管理"))
    parser.add_argument("--shadow-dir", type=Path, default=PROJECT_ROOT / "data" / "shadow" / "atomic_evidence")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"knowledge root does not exist: {args.root}")

    files = [path for path in iter_source_files(args.root) if path.suffix.lower() in ATOMIC_EXTENSIONS]
    args.shadow_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.shadow_dir / "records.jsonl"
    statuses = Counter()
    types = Counter()
    granularities = Counter()
    metadata_review = Counter()
    errors: list[dict[str, Any]] = []
    record_count = 0
    location_complete = 0
    xlsx_exact_rows = 0
    with output_path.open("w", encoding="utf-8") as output:
        for path in files:
            result = build_atomic_evidence(path, args.root)
            statuses[result["status"]] += 1
            types[result["file_type"]] += 1
            if result.get("error"):
                errors.append({"path": result["path"], "status": result["status"], "error": result["error"]})
            for record in result.get("records", []):
                output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                record_count += 1
                granularities[record["granularity"]] += 1
                location_complete += int(bool(record.get("location")))
                if record["granularity"] == "row" and record["location"].get("row_start") == record["location"].get("row_end"):
                    xlsx_exact_rows += 1
                metadata_review[str((record.get("metadata") or {}).get("metadata_review_status") or "UNKNOWN")] += 1

    report = {
        "root": str(args.root),
        "shadow_output": str(output_path.resolve()),
        "source_files": len(files),
        "records": record_count,
        "file_type_counts": dict(types),
        "status_counts": dict(statuses),
        "granularity_counts": dict(granularities),
        "location_complete_records": location_complete,
        "xlsx_exact_row_records": xlsx_exact_rows,
        "metadata_review_status_counts": dict(metadata_review),
        "errors": errors,
        "formal_qdrant_written": False,
        "llm_called": False,
    }
    report_path = PROJECT_ROOT / "docs" / "KNOWLEDGE_ATOMIC_EVIDENCE_SHADOW_REPORT.md"
    report_path.write_text(render_report(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"records={output_path.resolve()}")
    print(f"report={report_path.resolve()}")
    return 0 if not errors else 1


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Shadow 原子证据层构建报告",
        "",
        "> 本报告验证 Markdown、XLSX、PDF、DOCX、PPTX 的 Shadow 原子证据；未接入正式 Retriever，未写入正式 Qdrant，未调用 LLM。",
        "",
        "## 1. 构建结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 知识源 | `{report['root']}` |",
        f"| 处理文件数 | {report['source_files']} |",
        f"| 原子证据记录数 | {report['records']} |",
        f"| location 完整记录 | {report['location_complete_records']} |",
        f"| XLSX 精确单行记录 | {report['xlsx_exact_row_records']} |",
        f"| LLM 调用 | {report['llm_called']} |",
        f"| 正式 Qdrant 写入 | {report['formal_qdrant_written']} |",
        "",
        "## 2. 文件类型和粒度",
        "",
        "| 类型 | 文件数 |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(report["file_type_counts"].items()))
    lines.extend(["", "| 原子粒度 | 记录数 |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(report["granularity_counts"].items()))
    lines.extend(["", "## 3. 状态和异常", "", "| 状态 | 文件数 |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(report["status_counts"].items()))
    if report["errors"]:
        lines.extend(["", "### 异常文件", ""])
        lines.extend(f"- `{item['path']}`：`{item['status']}`；{item['error']}" for item in report["errors"])
    lines.extend(
        [
            "",
            "## 4. 这次验证证明了什么",
            "",
            "- Markdown 事实不再只能依赖多行 Chunk；每个非空行都有独立 `evidence_id` 和单行 location。",
            "- XLSX 数据不再只能依赖整 Sheet Chunk；每个非空行保留 Sheet、行号、表头和单元格字段。",
            "- PDF、DOCX、PPTX 证据保留页、段落/表格行、幻灯片和文本行位置；扫描 PDF 仍标记为 `needs_ocr`。",
            "- 原子证据仍然只是 Shadow 数据层，尚未改变正式检索排序和回答链路。",
            "- 原子记录存在不等于业务语义已经确认；字段含义、版本和权限仍需治理。",
            "",
            "## 5. 下一步",
            "",
            "1. 用真实业务问题回放原子证据层，确认目标句/目标行是否能被精确命中。",
            "2. 继续细化 PDF 页内段落、DOCX 表格单元格和 PPTX 文本框位置。",
            "3. 通过 Shadow A/B 验证后，才考虑接入新的 Retriever。",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
