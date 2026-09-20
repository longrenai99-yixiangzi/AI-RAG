from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.atomic_search import search_atomic_evidence
from app.trial.v2 import _rank_atomic_candidates


OUTPUT = ROOT / "evaluation" / "knowledge_os_optimization" / "method_ab_comparison.json"


def main() -> int:
    question = "区域公司中心可以额外设什么岗位？"
    raw = "区域分公司中心选择设置技术投标岗、钢筋翻样岗。"
    baseline = {"evidence_id": "E1", "source_id": "S1", "source_version": "V1", "text": raw, "raw_text": raw, "file_name": "制度.pdf"}
    contextual = {**baseline, "search_context": "区域公司中心 可选岗位 额外设置"}
    variant = {**baseline, "search_context": question}
    child = {"evidence_id": "C1", "source_id": "S1", "source_version": "V1", "parent_evidence_id": "P1", "text": "技术投标岗、钢筋翻样岗", "raw_text": "技术投标岗、钢筋翻样岗", "file_name": "制度.pdf"}
    parent = {"evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": raw, "raw_text": raw, "file_name": "制度.pdf"}
    stages = {
        "baseline": search_atomic_evidence(question, [baseline]),
        "question_variant": search_atomic_evidence(question, [variant]),
        "search_context": search_atomic_evidence(question, [contextual]),
        "parent_completion": _rank_atomic_candidates(question, [child], {"C1": child, "P1": parent}),
        "combined": _rank_atomic_candidates(question, [variant, variant, child], {"E1": variant, "C1": child, "P1": parent}),
    }
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fixed_conditions": {"question": question, "source_version": "V1", "candidate_budget": 40, "model": "not_used"},
        "stages": {
            name: {
                "candidate_count": len(rows),
                "top_score": float(rows[0].get("score") or 0) if rows else 0,
                "evidence_ids": [str((row.get("record") or row).get("evidence_id")) for row in rows],
                "raw_text_unchanged": all(str((row.get("record") or row).get("raw_text") or (row.get("record") or row).get("text")) in {raw, "技术投标岗、钢筋翻样岗"} for row in rows),
                "optional_condition_available": any("选择设置" in str((row.get("record") or row).get("text") or "") for row in rows),
            }
            for name, rows in stages.items()
        },
        "non_improving_samples": [],
        "interpretation": "最小夹具仅验证机制方向，不外推全库提升比例；公开业务题另行全库验收。",
    }
    assert payload["stages"]["question_variant"]["top_score"] > payload["stages"]["baseline"]["top_score"]
    assert payload["stages"]["search_context"]["top_score"] >= payload["stages"]["baseline"]["top_score"]
    assert payload["stages"]["parent_completion"]["optional_condition_available"]
    assert len(payload["stages"]["combined"]["evidence_ids"]) == len(set(payload["stages"]["combined"]["evidence_ids"]))
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["stages"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
