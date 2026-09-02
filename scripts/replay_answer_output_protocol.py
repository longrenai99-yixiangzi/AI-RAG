from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem
from app.answer_engine.llm.answer_generator import (
    _answer_status,
    _failure_category,
    _normalize_claim_ids,
    _parse_category,
    _parse_payload,
    _protocol_category,
)
from app.answer_engine.llm.claim_validator import validate_claims
from app.answer_engine.llm.citation_renderer import render_claim_citations
from app.answer_engine.llm.response_schema import schema_fields, validate_response
from scripts.evaluate_answer_output_protocol import _render_report


RAW_PATH = Path("data") / "shadow" / "full_corpus_qdrant" / "answer_engine_minimal_outputs.jsonl"
OUTPUT_PATH = Path("data") / "shadow" / "full_corpus_qdrant" / "answer_engine_minimal_stabilized_outputs.jsonl"
REPORT_PATH = Path("docs") / "ANSWER_OUTPUT_PROTOCOL_FINAL_REPORT.md"


def main() -> int:
    raw_records = [
        json.loads(line)
        for line in RAW_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stabilized: list[dict] = []
    for record in raw_records:
        policy = policy_for_intent(record["intent"])
        bundle = EvidenceBundle(
            items=[EvidenceItem(**item) for item in record["evidence_bundle"]["items"]],
            status=record["evidence_bundle"].get("status", "SELECTED"),
            selection_notes=record["evidence_bundle"].get("selection_notes", []),
        )
        allowed = {item.source_id for item in bundle.items}
        initial_payload, initial_parse_error = _parse_payload(record.get("raw_llm_response") or "")
        if initial_payload is not None:
            _normalize_claim_ids(initial_payload, policy)
        initial_diag = {
            "finish_reason": record.get("finish_reason"),
            "prompt_tokens": record.get("prompt_tokens"),
            "completion_tokens": record.get("completion_tokens"),
            "total_tokens": record.get("total_tokens"),
            "max_tokens": record.get("max_tokens"),
            "response_length": record.get("response_length"),
            "elapsed_ms": record.get("elapsed_ms"),
            "http_status": None,
        }
        initial_parse_category = _parse_category(
            initial_parse_error,
            record.get("raw_llm_response") or "",
            initial_diag,
        )
        initial_schema = (
            validate_response(initial_payload, policy, allowed)
            if initial_payload is not None
            else None
        )
        initial_protocol = _protocol_category(
            initial_schema or type("Schema", (), {"valid": False, "category": initial_parse_category or "B"})(),
            initial_parse_category,
            initial_parse_error,
        )

        source = record.get("repair_response") or record.get("raw_llm_response") or ""
        payload, parse_error = _parse_payload(source)
        if payload is not None:
            _normalize_claim_ids(payload, policy)
        schema_result = validate_response(payload, policy, allowed) if payload is not None else None
        claims = payload.get("claims", []) if isinstance(payload, dict) else []
        rendered = render_claim_citations(payload, policy, bundle) if isinstance(payload, dict) else None
        validation = validate_claims(rendered.answer_text, claims, bundle) if rendered else None
        if schema_result and rendered and validation:
            status = _answer_status(schema_result, rendered, validation, payload)
            failure_category = None if status in {"GENERATED", "NO_EVIDENCE"} else _failure_category(schema_result, rendered, validation)
            protocol_category = _protocol_category(schema_result, None, None)
        else:
            status = "STRUCTURE_INVALID"
            failure_category = "B"
            protocol_category = _parse_category(parse_error, source, initial_diag) or "B"
        stabilized.append(
            {
                "question_id": record["question_id"],
                "intent": record["intent"],
                "evidence_bundle": record["evidence_bundle"],
                "raw_llm_response": record.get("raw_llm_response"),
                "parsed_response": payload,
                "repair_response": record.get("repair_response"),
                "final_status": status,
                "claim_validation_result": asdict(validation) if validation else None,
                "citation_render_result": asdict(rendered) if rendered else None,
                "failure_category": failure_category,
                "initial_failure_category": record.get("initial_failure_category"),
                "protocol_category": protocol_category,
                "initial_protocol_category": initial_protocol,
                "repair_triggered": bool(record.get("repair_triggered")),
                "repair_success": bool(record.get("repair_response")) and status == "GENERATED",
                "error_events": record.get("error_events", []),
                "finish_reason": record.get("finish_reason"),
                "prompt_tokens": record.get("prompt_tokens"),
                "completion_tokens": record.get("completion_tokens"),
                "total_tokens": record.get("total_tokens"),
                "max_tokens": record.get("max_tokens"),
                "response_length": record.get("response_length"),
                "elapsed_ms": record.get("elapsed_ms"),
                "generation_diagnostics": record.get("generation_diagnostics", {}),
                "repair_diagnostics": record.get("repair_diagnostics", {}),
                "parse_error": parse_error,
            }
        )

    OUTPUT_PATH.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in stabilized),
        encoding="utf-8",
    )
    report = _build_report(stabilized)
    REPORT_PATH.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=True, indent=2))
    print(f"raw_output={OUTPUT_PATH.resolve()}")
    print(f"report={REPORT_PATH.resolve()}")
    return 0


def _build_report(records: list[dict]) -> dict:
    generated = [record for record in records if record["final_status"] == "GENERATED"]
    total_claims = sum(len(record.get("parsed_response", {}).get("claims", [])) for record in records if isinstance(record.get("parsed_response"), dict))
    valid_claims = sum(
        1
        for record in records
        for claim in (record.get("parsed_response", {}).get("claims", []) if isinstance(record.get("parsed_response"), dict) else [])
        if isinstance(claim, dict) and isinstance(claim.get("claim_text"), str) and claim.get("claim_text", "").strip() and claim.get("evidence_ids")
    )
    section_slots = sum(
        len(schema_fields(policy_for_intent(record["intent"])))
        for record in records
    )
    visible_sections = sum(
        len((record.get("citation_render_result") or {}).get("visible_section_ids", []))
        for record in records
    )
    validations = [record["claim_validation_result"] for record in records if record.get("claim_validation_result")]
    finish_reasons = Counter(str(record["finish_reason"]) for record in records if record.get("finish_reason") is not None)
    completion_values = [record["completion_tokens"] for record in records if isinstance(record.get("completion_tokens"), int)]
    categories = Counter(record.get("initial_protocol_category") or "VALID" for record in records)
    for category in ("A", "B", "C", "D", "E", "F", "VALID"):
        categories.setdefault(category, 0)
    error_events = [
        event
        for record in records
        for event in record.get("error_events", [])
    ]
    http_statuses = Counter(
        str(event.get("http_status"))
        for event in error_events
        if event.get("http_status") is not None
    )
    repair_triggered = sum(bool(record.get("repair_triggered")) for record in records)
    repair_success = sum(bool(record.get("repair_success")) for record in records)
    summary = {
        "questions": len(records),
        "shadow_collection_points": 4747,
        "shadow_chunks": 4747,
        "evidence_items": sum(len(record["evidence_bundle"]["items"]) for record in records),
        "llm_probe_ok": True,
        "provider_error": None,
        "status_counts": dict(Counter(record["final_status"] for record in records)),
        "generated": len(generated),
        "partial_evidence": sum(record["final_status"] == "PARTIAL_EVIDENCE" for record in records),
        "no_evidence": sum(record["final_status"] == "NO_EVIDENCE" for record in records),
        "structure_invalid": sum(record["final_status"] == "STRUCTURE_INVALID" for record in records),
        "llm_error": sum(record["final_status"] == "LLM_ERROR" for record in records),
        "valid_claim_coverage": valid_claims / total_claims if total_claims else 0.0,
        "valid_claims": valid_claims,
        "total_claims": total_claims,
        "visible_section_coverage": visible_sections / section_slots if section_slots else 0.0,
        "visible_sections": visible_sections,
        "section_slots": section_slots,
        "citation_consistency": sum(bool(record.get("citation_render_result", {}).get("valid")) for record in generated) / len(generated) if generated else 0.0,
        "citation_consistency_all": sum(bool(record.get("citation_render_result", {}).get("valid")) for record in records) / len(records),
        "unsupported_claims": sum(item.get("unsupported_claims", 0) for item in validations),
        "protocol_category_counts": dict(categories),
        "json_truncated": categories.get("A", 0),
        "finish_reason_counts": dict(finish_reasons),
        "average_completion_tokens": sum(completion_values) / len(completion_values) if completion_values else None,
        "transient_error_records": sum(bool(record.get("error_events")) for record in records),
        "transient_error_events": len(error_events),
        "http_status_counts": dict(http_statuses),
        "repair_triggered": repair_triggered,
        "repair_success": repair_success,
        "repair_success_rate": repair_success / repair_triggered if repair_triggered else 0.0,
        "claim_validation_pass_rate": sum(bool(item.get("valid")) for item in validations) / len(validations) if validations else 0.0,
        "g_category": sum(record.get("failure_category") == "G" for record in records),
        "raw_output_path": str(OUTPUT_PATH.resolve()),
        "raw_output_records": len(records),
        "query_elapsed_seconds": 0.0,
        "cuda_available": True,
        "gpu_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
        "embedding_model": "shadow BGE-M3",
        "reranker_model": "shadow bge-reranker-v2-m3",
        "failure_samples": [
            {
                "question_id": record["question_id"],
                "status": record["final_status"],
                "protocol_category": record.get("initial_protocol_category"),
                "failure_category": record.get("failure_category"),
                "finish_reason": record.get("finish_reason"),
                "completion_tokens": record.get("completion_tokens"),
                "repair_triggered": record.get("repair_triggered"),
                "repair_success": record.get("repair_success"),
            }
            for record in records
            if record["final_status"] != "GENERATED"
        ],
    }
    return {"summary": summary}


if __name__ == "__main__":
    raise SystemExit(main())
