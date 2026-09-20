from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
INPUT = V26 / "v2_6_2_compatibility_replay.json"
OUTPUT = V26 / "v2_6_2_compatibility_failure_clusters.json"
REPORT = ROOT / "docs" / "V2_6_2_COMPATIBILITY_FAILURE_CLUSTERS.md"


def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    clusters: dict[str, list[dict]] = {
        "SOURCE_COVERAGE_OR_EVIDENCE_ROLE_GAP": [],
        "MULTI_FACT_COVERAGE_GAP": [],
        "MALFORMED_OR_EMPTY_QUERY": [],
        "ANSWERED_REQUIRES_FACT_AND_SOURCE_REVIEW": [],
    }
    for record in records:
        bundle = str(record.get("current_bundle_status") or "")
        status = str(record.get("current_status") or "")
        question = str(record.get("question") or "").strip()
        if len(question) < 2 or not any(char.isalnum() or "\u3400" <= char <= "\u9fff" for char in question):
            category = "MALFORMED_OR_EMPTY_QUERY"
        elif bundle == "INSUFFICIENT_EVIDENCE":
            category = "SOURCE_COVERAGE_OR_EVIDENCE_ROLE_GAP"
        elif bundle == "VERIFIED_PARTIAL" or status == "PARTIAL_ANSWER":
            category = "MULTI_FACT_COVERAGE_GAP"
        else:
            category = "ANSWERED_REQUIRES_FACT_AND_SOURCE_REVIEW"
        clusters[category].append({
            "question_hash": record.get("question_hash"),
            "question": record.get("question"),
            "current_status": status,
            "current_bundle_status": bundle,
            "citation_count": len(record.get("current_citations") or []),
        })
    summary = {key: len(value) for key, value in clusters.items()}
    result = {
        "schema_version": "knowledge_os_v2_6_2.compatibility_failure_clusters",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": payload.get("current_candidate_hash"),
        "historical_question_count": len(records),
        "summary": summary,
        "interpretation": {
            "source_gap": "需要补充或修正来源正文、项目范围、表格/段落角色；不能靠改写答案解决。",
            "coverage_gap": "同一问题已有部分直接证据，但多事实、多指标或多子问题未覆盖完整。",
            "manual_review": "ANSWERED 只表示形成了回答和引用，不等于事实与来源已人工确认。",
        },
        "shared_repair_targets": [
            "先修来源正文 admission、项目/年份范围和 Evidence Role，不为单题硬编码答案。",
            "再修多事实/枚举问题的 coverage map 与答案完整性校验。",
            "最后对 ANSWERED 全量进行事实、来源文件和定位人工复核；不把离线状态当作通过。",
        ],
        "clusters": clusters,
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text("\n".join([
        "# V2.6.2 历史问题兼容性失败聚类",
        "",
        f"- 候选哈希：`{result['candidate_hash']}`",
        f"- 历史问题：`{result['historical_question_count']}`",
        f"- 聚类计数：`{summary}`",
        "",
        "## 结论",
        "",
        "1. `SOURCE_COVERAGE_OR_EVIDENCE_ROLE_GAP` 必须补正文、范围或证据角色，不能靠答案模板掩盖。",
        "2. `MULTI_FACT_COVERAGE_GAP` 要修共享 coverage map 和完整性校验，避免只答到一个指标。",
        "3. `ANSWERED_REQUIRES_FACT_AND_SOURCE_REVIEW` 仍未逐题人工确认，不能标记为全库正确。",
        "",
        "该报告是离线诊断，不替代 8010 Live Shadow，也不授权 8000。",
        "",
    ]), encoding="utf-8")
    print(json.dumps({"candidate_hash": result["candidate_hash"], "historical_question_count": result["historical_question_count"], "summary": summary, "output": str(OUTPUT), "report": str(REPORT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
