from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.trial.runtime_reporting import traffic_kind


SCHEMA_VERSION = "knowledge_growth.v1.1"
_LOCK = threading.Lock()
EXCLUDED_TOPICS = ('科研成果总结', '科技研发管理', '结题验收')


def within_growth_scope(question: str) -> bool:
    return not any(topic in question for topic in EXCLUDED_TOPICS)


def candidate_for_trace(trace: dict[str, Any]) -> dict[str, Any] | None:
    if traffic_kind(trace) != 'REAL':
        return None
    if not within_growth_scope(str(trace.get('resolved_question') or trace.get('question') or '')):
        return None
    answer = trace["answer"]
    bundle = trace["bundle"]
    status = answer["answer_status"]
    if status == "ANSWERED" and bundle["bundle_status"] == "VERIFIED":
        return None
    failure_type, growth_type, priority, reason, action = _classification(trace)
    fingerprint = _fingerprint(trace, failure_type)
    evidence = _evidence_snapshot(trace)
    affected = _affected(bundle)
    return {
        "candidate_id": "GC_" + fingerprint[:16], "candidate_fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(), "source_query_id": trace["question_id"], "question": trace["question"],
        "failure_type": failure_type, "growth_type": growth_type, "priority": priority, "reason": reason,
        "current_answer_status": status, "affected_document_ids": affected["document_ids"], "affected_section_ids": affected["section_ids"], "affected_evidence_ids": affected["evidence_ids"],
        "candidate_hash": trace.get('candidate_hash') or '', "traffic_kind": 'REAL',
        "automatic_knowledge_publish": 0, "runtime_input": False,
        "knowledge_gap": _knowledge_gap(trace, failure_type), "retrieval_gap": _retrieval_gap(trace, failure_type), "answer_gap": _answer_gap(trace, failure_type),
        "recommended_action": action, "suggested_source": _suggested_source(trace, failure_type), "suggested_metadata_fix": None, "suggested_qa": _suggested_qa(trace, failure_type),
        "evidence_snapshot": evidence, "governance_status": _governance_status(failure_type), "review_status": "PROPOSED", "reviewer": None, "review_comment": None,
        "created_by": "AI_PROPOSED", "knowledge_origin": "SOURCE_DERIVED" if any(row.get('excerpt') and row.get('source_version') for row in evidence['sources']) else "AI_PROPOSED", "schema_version": SCHEMA_VERSION, "occurrence_count": 1, "latest_seen_at": datetime.now(timezone.utc).isoformat(), "related_query_ids": [trace["question_id"]], "regression_question_ids": [trace["question_id"]],
    }


def merge_candidate(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if existing['candidate_fingerprint'] != incoming['candidate_fingerprint']:
        raise ValueError('CANDIDATE_VERSION_OR_SCOPE_MISMATCH')
    merged = dict(existing)
    query_ids = set(existing.get('related_query_ids') or []) | set(incoming.get('related_query_ids') or [])
    if query_ids == set(existing.get('related_query_ids') or []):
        return merged
    merged["occurrence_count"] = len(query_ids)
    merged["latest_seen_at"] = incoming["latest_seen_at"]
    merged["related_query_ids"] = sorted(query_ids)
    merged['regression_question_ids'] = sorted(set(existing.get('regression_question_ids') or []) | set(incoming.get('regression_question_ids') or []))
    return merged


def save_candidate(path: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Append a new snapshot once per query; existing reviews are separate and untouched."""
    # shortcut: one writer process per directory; CLI replays must use a separate output directory.
    with _LOCK:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []
        previous = next((row for row in reversed(rows) if row['candidate_fingerprint'] == candidate['candidate_fingerprint']), None)
        updated = merge_candidate(previous, candidate) if previous else candidate
        if updated != previous:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(updated, ensure_ascii=False)+'\n')
        return updated


def trace_from_runtime(audit: dict[str, Any], trace: dict[str, Any], source_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use recorded metadata, never reconstruct source quotations from generated claims."""
    if audit['query_run_id'] != trace.get('query_run_id'):
        raise ValueError('TRACE_QUERY_ID_MISMATCH')
    manifest = source_manifest or {}
    if manifest and trace.get('candidate_hash') != manifest.get('candidate_hash'):
        raise ValueError('TRACE_CANDIDATE_VERSION_MISMATCH')
    sources = {row['source_id']:row for row in manifest.get('sources') or []}
    stages = trace.get('stages') or {}
    plan = dict(stages.get('query_understanding') or {})
    plan['specialty'] = plan.get('specialty') or plan.get('professional') or []
    periods = ((stages.get('retrieval_plan') or {}).get('hard_filters') or {}).get('period') or []
    plan['period'] = plan.get('period') or (periods[0] if len(periods)==1 else '')
    records = []
    for row in stages.get('evidence_validation') or []:
        source = sources.get(row.get('source_id'), {})
        records.append({
            'evidence_id':row.get('chunk_id'), 'document_id':row.get('document_id'), 'source_id':row.get('source_id'),
            'source_path':row.get('source_path') or source.get('source_path'),
            'source_version':row.get('source_version') or source.get('sha256'),
            'file_name':row.get('file_name'), 'location':row.get('display_location'),
            'role':row.get('role'), 'scope':row.get('scope_fields') or {}, 'text':'',
        })
    return {
        'question_id':audit['query_run_id'], 'question':audit['question'],
        'resolved_question':audit.get('resolved_question') or audit['question'], 'traffic_kind':traffic_kind(audit),
        'candidate_hash':trace.get('candidate_hash') or '', 'failure':trace.get('failure') or {},
        'answer':{'answer_status':trace['answer_status'], 'claims':[]},
        'bundle':{'bundle_status':trace.get('bundle_status') or '', 'query_plan':plan,
                  'coverage_map':stages.get('coverage_map') or [], 'candidate_evidence':records,
                  'verified_evidence':[row for row in records if row['role']=='DIRECT'], 'conflicting_evidence':[]},
    }


def _classification(trace: dict[str, Any]) -> tuple[str, str, str, str, str]:
    answer = trace["answer"]
    bundle = trace["bundle"]
    status = answer["answer_status"]
    failure = str((trace.get('failure') or {}).get('failure_code') or '')
    if failure in {'RECALL_MISS','RERANK_FAIL','INDEX_MISSING','PARSE_FAILED','OCR_FAILED','STRUCTURE_LOST','TABLE_CONTEXT_LOST','CHUNK_MISSING','CHUNK_CONTEXT_MISSING','METADATA_ERROR','SOURCE_VERSION_ERROR','SCOPE_MISMATCH_FALSE_REJECT','EVIDENCE_FALSE_REJECT'}:
        return failure, 'RETRIEVAL_GROWTH', 'P1', '需先检查来源、解析、索引或检索链路，不能把系统问题编成标准答案。', '定位已有资料与运行版本，修复对应链路，再回放原问题。'
    if status == "SOURCE_SCOPE_MISSING":
        return "SOURCE_SCOPE_MISSING", "KNOWLEDGE_GROWTH", "P1", "本次运行没有取得该范围的直接依据；不据此断言原件或库内没有资料。", "先核对来源归属、版本与检索；确有资料缺口后再准备补充来源。"
    if status == "CONFLICTING_ANSWER" or bundle["bundle_status"] == "CONFLICTING_EVIDENCE":
        return "CONFLICTING_EVIDENCE", "CONFLICT_REVIEW_CANDIDATE", "P0", "同范围事实存在冲突，系统不能自动裁决。", "由业务负责人确认正确口径，或补充版本、时间和指标定义。"
    if status == 'ANSWER_VALIDATION_FAILED' or failure in {'ANSWER_SYNTHESIS_FAIL','ANSWER_MISSING_FACT','ANSWER_UNSUPPORTED_CLAIM','CITATION_VALIDATION_FAIL','FEEDBACK_NOT_EFFECTIVE'}:
        return failure or 'ANSWER_VALIDATION_FAILED', 'QA_GROWTH', 'P0', '需修复回答、引用或反馈生效链路，不能自动新增标准答案。', '核对同版证据与回答，修复后回归原问题。'
    if status == "PARTIAL_ANSWER" or status == 'INSUFFICIENT_EVIDENCE' or bundle["bundle_status"] in {"VERIFIED_PARTIAL", "INSUFFICIENT_EVIDENCE"}:
        return "INSUFFICIENT_EVIDENCE", "EVIDENCE_REVIEW_CANDIDATE", "P1", "需区分资料缺项、正常拒答与已有依据未被正确使用。", "先核原问题、同项目同版原件及回答覆盖；有资料则修复读取或问答，无资料才补充，不自动生成事实。"
    if status == "ANSWER_VALIDATION_FAILED":
        return "ANSWER_VALIDATION_FAILED", "QA_GROWTH", "P0", "答案未通过校验，不能作为可信输出。", "检查 Claim、Citation 和回答模板，不修改正式规则前先完成 Shadow 回归。"
    return "ANSWER_GAP", "QA_GROWTH", "P2", "回答状态异常，需要人工检查表达和 Claim 覆盖。", "审核问答模板与必需证据类型。"


def _knowledge_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type == "SOURCE_SCOPE_MISSING":
        return "需要与问题直接对应的正式业务来源；当前治理范围内未发现可用正文。"
    if failure_type == "INSUFFICIENT_EVIDENCE":
        uncovered = [item.get("subquestion") for item in trace["bundle"].get("coverage_map", []) if item.get("coverage_status") == "EVIDENCE_INSUFFICIENT"]
        limitations = [claim.get("rendered_claim_text") for claim in trace["answer"].get("claims", []) if claim.get("claim_type") in {"LIMITATION", "INSUFFICIENT"}]
        return "；".join(filter(None, [*uncovered, *limitations])) or "缺少可验证字段或结构化证据。"
    return None


def _retrieval_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type in {"DOCUMENT_MISSED", "SECTION_MISSED", "TABLE_MISSED", "EVIDENCE_MISSED"}:
        return "正确来源存在但未进入对应检索阶段。"
    return None


def _answer_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type == "CONFLICTING_EVIDENCE":
        return "需要冲突事实的业务口径确认，不能由答案层自动选择。"
    if failure_type == "INSUFFICIENT_EVIDENCE":
        return "已回答部分事实，但缺失字段不得被补全。"
    return None


def _suggested_source(trace: dict[str, Any], failure_type: str) -> dict[str, Any] | None:
    if failure_type != "SOURCE_SCOPE_MISSING":
        return None
    return {"required_source_type": "正式制度、项目资料或结构化台账", "current_root_status": "NO_APPROVED_SOURCE_IN_CURRENT_SCOPE", "known_owner_source": None, "governance_approval_required": True}


def _suggested_qa(trace: dict[str, Any], failure_type: str) -> dict[str, Any] | None:
    if failure_type != "INSUFFICIENT_EVIDENCE":
        return None
    return {"canonical_question": trace["question"], "expected_answer_type": "FIELD_BACKED_FACT", "required_evidence_type": "STRUCTURED_TABLE_OR_EXPLICIT_FIELD", "ownership": "AI_PROPOSED"}


def _governance_status(failure_type: str) -> str:
    if failure_type == "SOURCE_SCOPE_MISSING":
        return "REQUIRES_SOURCE_GOVERNANCE_REVIEW"
    if failure_type == "CONFLICTING_EVIDENCE":
        return "REQUIRES_BUSINESS_CONFLICT_REVIEW"
    return "REQUIRES_EVIDENCE_COMPLETENESS_REVIEW"


def _affected(bundle: dict[str, Any]) -> dict[str, list[str]]:
    candidates = bundle.get("candidate_evidence", [])
    return {"document_ids": sorted({str(item["document_id"]) for item in candidates if item.get("document_id")}), "section_ids": sorted({str(item["section_id"]) for item in candidates if item.get("section_id")}), "evidence_ids": sorted({str(item["evidence_id"]) for item in candidates if item.get("evidence_id")})}


def _evidence_snapshot(trace: dict[str, Any]) -> dict[str, Any]:
    bundle = trace["bundle"]
    evidence = bundle.get("conflicting_evidence") or bundle.get("verified_evidence") or bundle.get("candidate_evidence", [])[:3]
    return {"bundle_status": bundle["bundle_status"], "query_scope": {key: bundle.get('query_plan', {}).get(key, []) for key in ('organization','project','year','period','specialty','metric')}, "coverage_map": bundle.get("coverage_map", []), "sources": [{"evidence_id": item.get("evidence_id"), "source_id":item.get('source_id'), "source_version":item.get('source_version'), "file_name": item.get("file_name"), "source_path": item.get("source_path"), "location": item.get("location"), "document_role": item.get("document_role"), "authority": item.get("authority"), "scope": item.get("scope"), "excerpt": _excerpt(item.get("raw_text") or item.get("text") or "")} for item in evidence]}


def _fingerprint(trace: dict[str, Any], failure_type: str) -> str:
    bundle = trace["bundle"]
    target = next((item.get("document_id") for item in bundle.get("verified_evidence", []) if item.get("document_id")), "")
    gap = _knowledge_gap(trace, failure_type) or _retrieval_gap(trace, failure_type) or _answer_gap(trace, failure_type) or ""
    normalized = re.sub(r"\s+", "", trace.get('resolved_question') or trace["question"]).casefold()
    scope = {key: bundle.get('query_plan', {}).get(key, []) for key in ('organization','project','year','period','specialty','metric')}
    versions = sorted({(str(item.get('source_path') or '').replace('\\','/').casefold(), str(item.get('source_version') or '')) for item in bundle.get('verified_evidence') or bundle.get('candidate_evidence') or []})
    identity = [normalized, failure_type, target, gap, trace.get('candidate_hash') or '', scope, versions]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _excerpt(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())[:360]
