from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REVIEW = V26 / "live_shadow_v2_6_1_manual_review.json"
BENCHMARK = ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
APPROVED = Path(r"D:\设计管理\.ai-growth\parsed\approved-sources")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    gold = {}
    for line in BENCHMARK.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        gold[row.get("question")] = row
    staged = [json.loads(line) for line in (STAGING / "documents.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    records = []
    for item in review.get("records") or []:
        reference = gold.get(item.get("question")) or {}
        basenames = reference.get("expected_source_basenames") or []
        stage_matches = [row for row in staged if any(str(row.get("file_name") or "").casefold() == str(name).casefold() for name in basenames)]
        physical = []
        for name in basenames:
            candidate = APPROVED / name
            if candidate.is_file():
                physical.append(candidate)
        classification = "EXACT_BODY_IN_CANDIDATE" if any(row.get("document_type") not in {"REGISTER_PAGE", "QUERY_PAGE"} for row in stage_matches) else "REGISTRATION_OR_QUERY_ONLY_IN_CANDIDATE" if stage_matches else "PHYSICAL_GOLD_NOT_IN_CANDIDATE" if physical else "PHYSICAL_GOLD_NOT_FOUND"
        records.append({"review_id": item["review_id"], "question": item.get("question"), "gold_qid": reference.get("question_id"), "expected_source_basenames": basenames, "stage_matches": [{"file_name": row.get("file_name"), "source_path": row.get("source_path"), "document_type": row.get("document_type"), "parse_status": row.get("parse_status")} for row in stage_matches], "physical_gold_matches": [{"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha(path)} for path in physical], "classification": classification, "approval_required": classification == "PHYSICAL_GOLD_NOT_IN_CANDIDATE"})
    result = {"schema_version": "knowledge_os_v2_6_1.gold_source_coverage", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "base_candidate": "V2.5_FROZEN", "records": records, "summary": {"record_count": len(records), "exact_body_in_candidate": sum(row["classification"] == "EXACT_BODY_IN_CANDIDATE" for row in records), "registration_or_query_only": sum(row["classification"] == "REGISTRATION_OR_QUERY_ONLY_IN_CANDIDATE" for row in records), "physical_gold_not_in_candidate": sum(row["classification"] == "PHYSICAL_GOLD_NOT_IN_CANDIDATE" for row in records), "physical_gold_not_found": sum(row["classification"] == "PHYSICAL_GOLD_NOT_FOUND" for row in records), "approval_required_count": sum(row["approval_required"] for row in records)}}
    out = V26 / "gold_source_coverage_v2_6_1.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 Gold 来源覆盖审计", "", f"- 审计问题数：`{result['summary']['record_count']}`", f"- 候选正文已存在：`{result['summary']['exact_body_in_candidate']}`", f"- 仅登记页/查询页：`{result['summary']['registration_or_query_only']}`", f"- 物理 Gold 存在但未入候选：`{result['summary']['physical_gold_not_in_candidate']}`", f"- 物理 Gold 未找到：`{result['summary']['physical_gold_not_found']}`", "", "未入候选的物理 Gold 只登记为待审批，不自动进入运行时。", ""]
    for row in records:
        lines += [f"## {row['review_id']}（{row['gold_qid']}）", "", f"- 分类：`{row['classification']}`", f"- 目标文件：`{row['expected_source_basenames']}`", f"- 候选匹配：`{row['stage_matches']}`", f"- 物理匹配：`{row['physical_gold_matches']}`", ""]
    (ROOT / "docs" / "V2_6_1_GOLD_SOURCE_COVERAGE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
