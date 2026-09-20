from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
INPUT = V26 / "v2_6_2_source_gap_queue.json"
OUT = V26 / "v2_6_2_source_role_batches.json"


def main() -> int:
    queue = json.loads(INPUT.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in queue.get("queue") or []:
        files = sorted({str(source.get("file_name") or "NO_SOURCE") for source in item.get("sources") or []})
        key = files[0] if len(files) == 1 else "MULTI_SOURCE_REVIEW"
        groups[key].append(item)
    batches = []
    for file_name, items in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        paths = sorted({str(source.get("source_path") or "") for item in items for source in item.get("sources") or [] if source.get("source_path")})
        batches.append({
            "file_name": file_name,
            "question_count": len(items),
            "physical_paths": paths,
            "physical_exists": all(bool(source.get("physical_exists")) for item in items for source in item.get("sources") or []),
            "governance_action": "ROW_LEVEL_SOURCE_ROLE_AND_LOCATION_REVIEW" if file_name.lower().endswith((".xlsx", ".xls", ".docx", ".pptx", ".pdf")) else "BODY_SECTION_ROLE_REVIEW",
            "questions": [{"question_hash": item.get("question_hash"), "question": item.get("question")} for item in items],
        })
    result = {
        "schema_version": "knowledge_os_v2_6_2.source_role_batches",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": queue.get("candidate_hash"),
        "question_count": queue.get("question_count"),
        "batch_count": len(batches),
        "all_physical_sources_exist": all(batch["physical_exists"] for batch in batches),
        "priority_order": "先处理高频台账/表格的行级证据，再处理单一正文页面；不将聚合问题的任意一行升级为答案。",
        "batches": batches,
        "formal_8000_touched": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidate_hash": result["candidate_hash"], "question_count": result["question_count"], "batch_count": result["batch_count"], "top_batches": [{"file_name": b["file_name"], "question_count": b["question_count"]} for b in batches[:10]], "out": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
