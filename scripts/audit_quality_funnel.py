"""Build comparable before/after quality funnels from persisted audit evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "evaluation" / "knowledge_os_system_audit"


def main() -> int:
    source = _read(AUDIT / "t01" / "source_coverage.json")
    before_validator = _read(AUDIT / "t06" / "validator_first_run.json")
    after_validator = _read(AUDIT / "t06" / "validator_audit.json")
    retrieval = _read(AUDIT / "t05" / "retrieval_model_audit.json")
    chunks = _read(AUDIT / "t02" / "chunk_audit_summary.json")
    before = _funnel(before_validator, source_available=sum(row.get("body_chars", 0) >= 80 for row in source.get("rows", [])))
    after = _funnel(after_validator, source_available=sum(row.get("codes") == ["OK"] for row in source.get("rows", [])))
    losses = {
        "SOURCE_BODY_MISSING": after["questions"] - after["source_available"],
        "RECALL_MISS": after["source_available"] - after["correct_source_recalled"],
        "RERANK_OR_TOPK_FAIL": after["correct_source_recalled"] - after["correct_source_top10"],
        "EVIDENCE_FALSE_REJECT": after["correct_source_top10"] - after["evidence_pass"],
        "ANSWER_OR_CITATION_SELECTION": after["evidence_pass"] - after["final_expected_source"],
    }
    payload = {
        "task": "KNOWLEDGE_OS_QUALITY_FUNNEL", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "label_status": "PROVISIONAL_GOLD_EXPECTED_FILES; alternative valid sources may be undercounted",
        "before": before, "after": after,
        "before_after": {key: {"before": before[key], "after": after[key], "delta": after[key] - before[key]} for key in ("source_available", "correct_source_recalled", "correct_source_top10", "evidence_pass", "final_expected_source")},
        "current_disjoint_loss_by_stage": losses,
        "root_cause_ranking": [{"rank": index, "code": code, "lost_questions": count} for index, (code, count) in enumerate(sorted(losses.items(), key=lambda item: (-item[1], item[0])), start=1)],
        "model_metrics": retrieval.get("metrics") or {},
        "chunk_metrics": chunks.get("metrics") or {},
        "interpretation": [
            "新增原文只读接入解决了大部分 Source Body 缺失，但没有修复冻结 section 索引。",
            "真实 Reranker 低于 Hybrid，当前不得接入在线链路。",
            "下一优先级由当前损失数决定：Recall、TopK/排序、答案证据选择、Evidence Validator。",
        ],
    }
    out = AUDIT / "quality_funnel.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"before": before, "after": after, "root_causes": payload["root_cause_ranking"]}, ensure_ascii=False))
    return 0


def _funnel(audit: dict, *, source_available: int) -> dict:
    rows = audit.get("rows") or []
    recalled = sum(bool(row.get("correct_source_recalled")) for row in rows)
    top10 = sum(bool(row.get("correct_source_in_validation_window")) if "correct_source_in_validation_window" in row else bool(row.get("correct_source_recalled") and 0 < int(row.get("correct_source_first_rank") or 0) <= 10) for row in rows)
    evidence = sum(bool(row.get("correct_evidence_accepted")) for row in rows)
    final = sum(bool(row.get("final_expected_source_hit")) for row in rows)
    return {"questions": len(rows), "source_available": source_available, "correct_source_recalled": recalled, "correct_source_top10": top10, "evidence_pass": evidence, "final_expected_source": final}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
