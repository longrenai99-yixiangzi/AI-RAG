"""Audit Scope/Evidence false rejects against provisional expected-source labels."""

from __future__ import annotations

import json
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t06"
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
SOURCE_AUDIT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t01" / "source_coverage.json"
ENDPOINT = "http://127.0.0.1:8010/api/v2/query"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-process", action="store_true")
    args = parser.parse_args()
    questions = [row for row in (yaml.safe_load(GOLD.read_text(encoding="utf-8")) or {}).get("questions", []) if row.get("question") and row.get("expected_files")]
    source_rows = (_read_json(SOURCE_AUDIT).get("rows") or [])
    linked_names = {(str(row.get("question_id")), _name(row.get("expected_source"))): {_name(Path(target).name) for target in row.get("linked_targets", [])} for row in source_rows}
    rows = []
    engine = None
    if args.in_process:
        from app.trial.v2 import V2TrialEngine
        engine = V2TrialEngine()
    with httpx.Client(timeout=180, trust_env=False) as client:
        for number, gold in enumerate(questions, start=1):
            if engine is not None:
                result = engine.answer(gold["question"], detect_growth=False)
            else:
                response = client.post(ENDPOINT, json={"question": gold["question"], "trial_user": "reviewer-001", "conversation_id": f"system-audit-t06-{gold['id']}"})
                response.raise_for_status()
                result = response.json()
            bundle = (result.get("debug") or {}).get("evidence_bundle") or {}
            candidates = bundle.get("candidate_evidence") or []
            expected = {_name(value) for value in gold["expected_files"]}
            for value in gold["expected_files"]:
                expected.update(linked_names.get((str(gold["id"]), _name(value)), set()))
            correct = [item for item in candidates if _name(item.get("file_name")) in expected]
            validation_window = [item for item in correct if int(item.get("candidate_rank") or 10**6) <= 10]
            accepted = [item for item in correct if item.get("role") == "DIRECT"]
            scope_rejected = [item for item in validation_window if "MISMATCH" in (item.get("scope") or {}).values()]
            evidence_rejected = [item for item in validation_window if item.get("role") != "DIRECT" and item not in scope_rejected]
            citations = result.get("citations") or []
            final_expected_hit = any(_name(item.get("file_name")) in expected for item in citations)
            rows.append({
                "question_id": gold["id"], "question": gold["question"], "expected_files": gold["expected_files"],
                "answer_status": result.get("answer_status"), "query_run_id": result.get("query_run_id"),
                "correct_source_recalled": bool(correct), "correct_source_first_rank": min((int(item.get("candidate_rank") or 10**6) for item in correct), default=0),
                "correct_source_in_validation_window": bool(validation_window), "rerank_fail": bool(correct and not validation_window),
                "correct_evidence_accepted": bool(accepted), "scope_false_reject": bool(correct and not accepted and scope_rejected),
                "evidence_false_reject": bool(validation_window and not accepted and evidence_rejected), "final_expected_source_hit": final_expected_hit,
                "provisional_false_accept": bool(citations and not final_expected_hit),
                "candidates": [_candidate(item, expected) for item in correct[:10]],
                "final_citations": [{key: item.get(key) for key in ("file_name", "source_id", "display_location", "source_version")} for item in citations],
            })
            if number % 10 == 0:
                print(f"[T06] {number}/{len(questions)}", flush=True)

    recalled = [row for row in rows if row["correct_source_recalled"]]
    validation_window = [row for row in rows if row["correct_source_in_validation_window"]]
    answered = [row for row in rows if row["final_citations"]]
    payload = {
        "task": "T06_SCOPE_EVIDENCE_VALIDATOR_AUDIT", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "RUN_PROVISIONAL_GOLD", "label_boundary": "expected_files 来自 provisional Gold；其他来源可能同样有效，false accept 需业务复核",
        "questions": len(rows),
        "correct_source_recall_rate": _rate(sum(row["correct_source_recalled"] for row in rows), len(rows)),
        "correct_source_top10_rate": _rate(len(validation_window), len(rows)),
        "rerank_fail_rate": _rate(sum(row["rerank_fail"] for row in recalled), len(recalled)),
        "evidence_pass_rate": _rate(sum(row["correct_evidence_accepted"] for row in validation_window), len(validation_window)),
        "scope_false_reject_rate": _rate(sum(row["scope_false_reject"] for row in validation_window), len(validation_window)),
        "evidence_false_reject_rate": _rate(sum(row["evidence_false_reject"] for row in validation_window), len(validation_window)),
        "final_expected_source_hit_rate": _rate(sum(row["final_expected_source_hit"] for row in rows), len(rows)),
        "provisional_false_accept_rate": _rate(sum(row["provisional_false_accept"] for row in answered), len(answered)),
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (OUT / f"validator_audit_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "validator_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    first = OUT / "validator_first_run.json"
    if not first.exists():
        first.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("questions", "correct_source_recall_rate", "correct_source_top10_rate", "rerank_fail_rate", "evidence_pass_rate", "scope_false_reject_rate", "evidence_false_reject_rate", "final_expected_source_hit_rate", "provisional_false_accept_rate")}, ensure_ascii=False))
    return 0


def _candidate(item: dict, expected: set[str]) -> dict:
    scope = item.get("scope") or {}
    return {"evidence_id": item.get("evidence_id"), "file_name": item.get("file_name"), "candidate_rank": item.get("candidate_rank"), "expected_evidence": _name(item.get("file_name")) in expected, "expected_scope": {key: "MATCH" for key, value in scope.items() if value not in {"NOT_APPLICABLE", None}}, "actual_scope": scope, "scope_result": "MISMATCH" if "MISMATCH" in scope.values() else "UNKNOWN" if "UNKNOWN" in scope.values() else "MATCH_OR_NOT_APPLICABLE", "actual_evidence": item.get("role"), "reject_reason": item.get("why_excluded") or item.get("why_context_only") or item.get("why_conflicting")}


def _name(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _rate(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / denominator, 4) if denominator else None}


def _read_json(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


if __name__ == "__main__":
    raise SystemExit(main())
