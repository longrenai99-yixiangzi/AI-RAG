from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def classify(record: dict[str, Any]) -> dict[str, str]:
    status = str(record.get("current_status") or "")
    bundle = str(record.get("current_bundle_status") or "")
    question = str(record.get("question") or "").strip()
    if len(question) < 2 or not any(c.isalnum() or "\u3400" <= c <= "\u9fff" for c in question):
        diagnosis, stage = "MALFORMED_OR_EMPTY_QUERY", "INPUT"
    elif status == "CONFLICTING_ANSWER" or bundle == "CONFLICTING_EVIDENCE":
        diagnosis, stage = "CONFLICT_REQUIRES_EVIDENCE_REVIEW", "EVIDENCE_CONFLICT"
    elif status == "INSUFFICIENT_EVIDENCE" and bundle == "VERIFIED":
        diagnosis, stage = "ANSWER_BUNDLE_STATUS_DISAGREEMENT", "ANSWER_RENDER_OR_VALIDATION"
    elif bundle == "INSUFFICIENT_EVIDENCE":
        diagnosis, stage = "SOURCE_COVERAGE_OR_EVIDENCE_ROLE_REVIEW", "EVIDENCE_BUNDLE"
    elif status == "PARTIAL_ANSWER":
        diagnosis, stage = "PARTIAL_CAUSE_NOT_CAPTURED", "NOT_DETERMINED_FROM_T5"
    elif status == "ANSWERED":
        diagnosis, stage = "ANSWERED_REQUIRES_FACT_AND_SOURCE_REVIEW", "MANUAL_REVIEW"
    elif status == "INSUFFICIENT_EVIDENCE":
        diagnosis, stage = "INSUFFICIENT_ANSWER_REQUIRES_SOURCE_REVIEW", "NOT_DETERMINED_FROM_T5"
    else:
        diagnosis, stage = "UNKNOWN_STATUS_REVIEW", "STATUS_MAPPING"
    bucket = {
        "ANSWERED": "ANSWERED", "PARTIAL_ANSWER": "PARTIAL",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT", "CONFLICTING_ANSWER": "CONFLICTING",
    }.get(status, "OTHER")
    return {
        "answer_status_bucket": bucket,
        "primary_diagnosis": diagnosis,
        "failure_stage": stage,
        "pending_reason": "T5缺少coverage map或显式Evidence Role，需结合题目和引用诊断。"
        if stage == "NOT_DETERMINED_FROM_T5" else "按primary_diagnosis处理。",
    }


def self_check() -> None:
    cases = [
        ("ANSWERED", "VERIFIED", "ANSWERED"), ("PARTIAL_ANSWER", "VERIFIED", "PARTIAL"),
        ("PARTIAL_ANSWER", "INSUFFICIENT_EVIDENCE", "PARTIAL"),
        ("INSUFFICIENT_EVIDENCE", "VERIFIED", "INSUFFICIENT"),
        ("CONFLICTING_ANSWER", "CONFLICTING_EVIDENCE", "CONFLICTING"),
        ("FUTURE_STATUS", "VERIFIED", "OTHER"),
    ]
    for status, bundle, expected in cases:
        got = classify({"question": "synthetic", "current_status": status, "current_bundle_status": bundle})
        assert got["answer_status_bucket"] == expected
        assert status == "ANSWERED" or got["answer_status_bucket"] != "ANSWERED"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def locations(citations: Any) -> list[dict[str, Any]]:
    fields = ("file_name", "source_path", "heading_path", "location", "page", "sheet", "row", "table", "column")
    return [
        {key: item.get(key) for key in fields if item.get(key) not in (None, "")}
        for item in (citations or []) if isinstance(item, dict)
    ]


def select_partials(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["answer_status"] == "PARTIAL_ANSWER":
            source = (row["evidence_locations"] or [{}])[0].get("file_name") or "NO_SOURCE"
            pools[(row["bundle_status"], source)].append(row)
    for pool in pools.values():
        pool.sort(key=lambda row: hashlib.sha256(str(row["question_hash"]).encode()).hexdigest())
    selected, keys = [], sorted(pools)
    while len(selected) < limit and any(pools.values()):
        for key in keys:
            if pools[key] and len(selected) < limit:
                selected.append(pools[key].pop(0))
    return selected


def main() -> int:
    self_check()
    parser = argparse.ArgumentParser(description="Classify an existing T5 result without rerunning retrieval or models.")
    parser.add_argument("--input", type=Path, default=V26 / "v2_6_2_compatibility_replay.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "logs" / "next_work" / "NEW-04")
    parser.add_argument("--gold", type=Path, default=V26 / "v2_6_2_answer_gold_replay.json")
    parser.add_argument("--exclusions", type=Path, default=V26 / "v2_6_2_owner_exclusions.json")
    parser.add_argument("--previous-clusters", type=Path, default=V26 / "v2_6_2_compatibility_failure_clusters.json")
    parser.add_argument("--representative-partials", type=int, default=20)
    args = parser.parse_args()

    payload, gold = read_json(args.input), read_json(args.gold)
    exclusions, previous = read_json(args.exclusions), read_json(args.previous_clusters)
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"input must contain a records list: {args.input}")

    gold_questions = {norm(row.get("question")) for row in gold.get("records", []) if isinstance(row, dict)}
    excluded = {str(row.get("question_hash")) for row in exclusions.get("records", []) if isinstance(row, dict)}
    duplicate_links = {
        str(row.get("duplicate_of_question_hash")) for row in exclusions.get("records", [])
        if isinstance(row, dict) and row.get("duplicate_of_question_hash")
    }
    rows, missing, hashes, normalized = [], [], Counter(), Counter()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            missing.append({"record_index": index, "fields": ["record_not_object"]})
            continue
        required = ("question_hash", "question", "current_status", "current_bundle_status", "current_citations")
        absent = [key for key in required if record.get(key) is None]
        if absent:
            missing.append({"record_index": index, "fields": absent})
        qhash, question = str(record.get("question_hash") or ""), record.get("question")
        hashes[qhash] += bool(qhash)
        normalized[norm(question)] += bool(norm(question))
        rows.append({
            "record_index": index,
            "question_hash": record.get("question_hash"),
            "question": question,
            "answer_status": record.get("current_status"),
            "bundle_status": record.get("current_bundle_status"),
            **classify(record),
            "evidence_role_capture": "NOT_CAPTURED_IN_T5",
            "evidence_locations": locations(record.get("current_citations")),
            "citation_count": len(record.get("current_citations") or []),
            "gold_mapping": "MAPPED" if norm(question) in gold_questions else None,
            "owner_exclusion_mapping": "DIRECT" if qhash in excluded else "DUPLICATE_OF" if qhash in duplicate_links else None,
        })

    answer_counts, bundle_counts = Counter(r["answer_status"] for r in rows), Counter(r["bundle_status"] for r in rows)
    diagnosis_counts = Counter(r["primary_diagnosis"] for r in rows)
    cross_tab = Counter((r["answer_status"], r["bundle_status"]) for r in rows)
    old_answered = (previous.get("clusters") or {}).get("ANSWERED_REQUIRES_FACT_AND_SOURCE_REVIEW", [])
    old_misclassified = sum(isinstance(r, dict) and r.get("current_status") != "ANSWERED" for r in old_answered)
    representative = select_partials(rows, max(0, args.representative_partials))
    handoff = {
        "conflicting": [r for r in rows if r["answer_status"] == "CONFLICTING_ANSWER"],
        "insufficient": [r for r in rows if r["answer_status"] == "INSUFFICIENT_EVIDENCE"],
        "representative_partials": representative,
        "selection_method": "Round-robin by bundle status and first cited source; stable hash order per group.",
    }
    result = {
        "schema_version": "knowledge_os_v2_6_2.compatibility_failure_clusters.new04",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": payload.get("current_candidate_hash"),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "record_count": len(records), "ledger_count": len(rows),
        "answer_status_counts": dict(sorted(answer_counts.items())),
        "bundle_status_counts": dict(sorted(bundle_counts.items())),
        "status_bundle_cross_tab": {f"{a}|{b}": n for (a, b), n in sorted(cross_tab.items())},
        "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
        "data_quality": {
            "missing_records": missing,
            "duplicate_question_hashes": sorted(key for key, count in hashes.items() if count > 1),
            "normalized_text_collision_count": sum(count > 1 for count in normalized.values()),
        },
        "mapping_summary": {
            "gold_records": len(gold.get("records", [])),
            "gold_mapped_to_t5": sum(r["gold_mapping"] is not None for r in rows),
            "owner_exclusion_records": len(exclusions.get("records", [])),
            "owner_exclusion_links_to_t5": sum(r["owner_exclusion_mapping"] is not None for r in rows),
        },
        "old_answered_cluster_non_answered_count": old_misclassified,
        "new09_handoff": handoff, "records": rows,
        "formal_8000_touched": False, "8010_switch_authorized": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output, report = args.output_dir / "compatibility_failure_clusters.json", args.output_dir / "classification_summary.md"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(
        "# NEW-04分类摘要\n\n"
        f"- 候选：{result['candidate_hash']}\n- 输入/台账：{len(records)}/{len(rows)}\n"
        f"- 答案状态：{result['answer_status_counts']}\n- Bundle状态：{result['bundle_status_counts']}\n"
        f"- 诊断：{result['diagnosis_counts']}\n- 旧ANSWERED组误分类：{old_misclassified}\n"
        f"- NEW-09交接：冲突{len(handoff['conflicting'])}、证据不足{len(handoff['insufficient'])}、代表性PARTIAL {len(representative)}。\n\n"
        "PARTIAL不会自动判为多事实召回失败；缺少coverage map和Evidence Role时保留待诊断状态。\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "record_count": len(records), "new09_partials": len(representative)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())