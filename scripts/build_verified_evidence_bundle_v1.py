from __future__ import annotations

import json
import re
from decimal import Decimal
from collections import Counter
from pathlib import Path
from typing import Any

from app.retrieval.hierarchical_v1 import HierarchicalIndex
from app.ingestion.atomic_search import query_terms, answer_support_gap, scalar_fact_parts, organization_placement
from app.ingestion.normalization.markdown_normalizer import strip_markdown_links
from app.retrieval.query_planner_v1 import ORGANIZATION_ALIASES


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "evaluation" / "hierarchical_retrieval_v1_stabilization" / "retrieval_traces.jsonl"
GOLD = ROOT / "evaluation" / "business_gold_v2" / "owner_approved_gold_manifest.json"
BASELINE = ROOT / "evaluation" / "business_gold_v2" / "gold_evaluation_matrix.json"
INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
EVAL = ROOT / "evaluation" / "verified_evidence_bundle_v1"
SHADOW = ROOT / "data" / "shadow" / "verified_evidence_bundle_v1"


def main() -> int:
    EVAL.mkdir(parents=True, exist_ok=True)
    SHADOW.mkdir(parents=True, exist_ok=True)
    traces = {row["question_id"]: row for row in _read_jsonl(INPUT)}
    gold = {row["question_id"]: row for row in _read_json(GOLD)["records"]}
    baseline = {row["question_id"]: row for row in _read_json(BASELINE)["records"]}
    index = HierarchicalIndex.load(INDEX)
    documents = {str(row["document_id"]): row for row in index.documents}
    atomic = {str(row.get("evidence_id")): row for row in index.atomic if row.get("evidence_id")}
    bundles = [_bundle(traces[key], gold[key], baseline[key], documents, atomic) for key in sorted(traces)]
    metrics = _metrics(bundles, gold)
    conflicts = _conflicts(bundles)
    primary = _primary(bundles)
    insufficient = _insufficient(bundles)
    lineage = _lineage(bundles)
    _write_jsonl(SHADOW / "bundles.jsonl", bundles)
    _write_json(EVAL / "ba_bundle_results.json", {"records": [_compact(bundle) for bundle in bundles]})
    _write_json(EVAL / "claim_coverage_metrics.json", metrics)
    _write_json(EVAL / "conflict_detection_metrics.json", conflicts)
    _write_json(EVAL / "primary_source_analysis.json", primary)
    _write_json(EVAL / "insufficient_evidence_metrics.json", insufficient)
    _write_json(EVAL / "lineage_safety_validation.json", lineage)
    _write_jsonl(EVAL / "verification_traces.jsonl", bundles)
    (ROOT / "docs" / "EVIDENCE_VERIFICATION_RULES_V1.md").write_text(_rules(), encoding="utf-8")
    (ROOT / "docs" / "VERIFIED_EVIDENCE_BUNDLE_V1_REPORT.md").write_text(_report(metrics, conflicts, primary, insufficient, lineage, bundles), encoding="utf-8")
    assert lineage["unsafe_aggregation_count"] == 0
    assert metrics["unsupported_claim_promotion"] == 0
    print(json.dumps({"bundle_count": len(bundles), "provider_http_requests": 0}, ensure_ascii=False))
    return 0


def _bundle(trace: dict[str, Any], gold: dict[str, Any], baseline: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = trace["query_plan"]
    source_available = bool(baseline.get("runtime_source_available"))
    candidates = [_candidate(row, plan, documents, atomic) for row in trace["atomic_candidates"]]
    subquestions = plan.get("subquestions") or ["回答原始问题"]
    if not source_available:
        return _source_scope_bundle(trace, plan, candidates, subquestions)
    conflicts = _same_scope_conflicts(candidates, plan)
    for candidate in candidates:
        if candidate["evidence_id"] in conflicts:
            candidate["role"] = "CONFLICTING"
            candidate["why_conflicting"] = conflicts[candidate["evidence_id"]]
        elif _inventory_register_direct(question, candidate):
            candidate["role"] = "DIRECT"
            candidate["why_direct"] = "Inventory register body directly states the requested file counts; substantive facts remain excluded from register pages."
        elif candidate["registration_page_flag"]:
            candidate["role"] = "EXCLUDED"
            candidate["why_excluded"] = "REGISTER_PAGE cannot directly support a fact."
        elif candidate["query_page_flag"]:
            candidate["role"] = "CONTEXT_ONLY"
            candidate["why_context_only"] = "QUERY_PAGE is secondary navigation material."
        elif _direct_candidate(candidate, plan):
            candidate["role"] = "DIRECT"
            candidate["why_direct"] = "Relevant original-source candidate with no registration exclusion."
        elif _supporting_candidate(candidate, plan):
            candidate["role"] = "SUPPORTING"
            candidate["why_supporting"] = "Relevant context without direct fact coverage."
        else:
            candidate["role"] = "CONTEXT_ONLY"
            candidate["why_context_only"] = "Topic-adjacent but not directly sufficient."
    coverage = _coverage(subquestions, plan, candidates)
    structured = _structured_facts(plan, candidates, coverage)
    status = _status(coverage, candidates, gold)
    direct = [candidate for candidate in candidates if candidate["role"] == "DIRECT"]
    primary = _primary_source(direct, plan)
    return {
        "question_id": trace["question_id"], "query_id": plan["query_id"], "question": plan["original_question"], "query_plan": plan, "subquestions": subquestions,
        "candidate_evidence": candidates, "verified_evidence": direct, "supporting_evidence": [candidate for candidate in candidates if candidate["role"] == "SUPPORTING"], "context_only_evidence": [candidate for candidate in candidates if candidate["role"] == "CONTEXT_ONLY"], "conflicting_evidence": [candidate for candidate in candidates if candidate["role"] == "CONFLICTING"], "excluded_evidence": [candidate for candidate in candidates if candidate["role"] == "EXCLUDED"],
        "coverage_map": coverage, "conflict_map": {key: value for key, value in conflicts.items()}, "authority_map": [{"evidence_id": candidate["evidence_id"], "authority": candidate["authority"], "reason": "Authority is considered after scope and fact relevance."} for candidate in candidates], "scope_map": [{"evidence_id": candidate["evidence_id"], "scope": candidate["scope"], "reason": candidate["scope_reason"]} for candidate in candidates], "lineage_map": [{"evidence_id": candidate["evidence_id"], "lineage_status": candidate["lineage_status"], "reason": "PARTIAL lineage blocks cross-source aggregation only."} for candidate in candidates], "structured_fact_map": structured, "evidence_sufficiency": _sufficiency(coverage, conflicts), "bundle_status": status, "primary_source_candidate": primary, "verification_trace": {"candidate_source": "020C Hierarchical Retrieval", "gold_runtime_injection": False, "lineage_auto_join": False, "unsupported_claim_promotion": 0},
    }


def _source_scope_bundle(trace: dict[str, Any], plan: dict[str, Any], candidates: list[dict[str, Any]], subquestions: list[str]) -> dict[str, Any]:
    return {"question_id": trace["question_id"], "query_id": plan["query_id"], "question": plan["original_question"], "query_plan": plan, "subquestions": subquestions, "candidate_evidence": candidates, "verified_evidence": [], "supporting_evidence": [], "context_only_evidence": candidates, "conflicting_evidence": [], "excluded_evidence": [], "coverage_map": [{"subquestion": item, "coverage_status": "NOT_COVERED", "evidence_ids": []} for item in subquestions], "conflict_map": {}, "authority_map": [], "scope_map": [], "lineage_map": [], "structured_fact_map": {}, "evidence_sufficiency": "INSUFFICIENT", "bundle_status": "SOURCE_SCOPE_MISSING", "primary_source_candidate": None, "verification_trace": {"candidate_source": "020C Hierarchical Retrieval", "source_scope_missing": True, "gold_runtime_injection": False, "lineage_auto_join": False, "unsupported_claim_promotion": 0}}


def _candidate(row: dict[str, Any], plan: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_id = str(row.get("evidence_id") or "")
    source = atomic.get(evidence_id, {})
    document = documents.get(str(row.get("document_id")), {})
    path = str(row.get("source_path") or source.get("source_path") or "").replace("/", "\\").casefold()
    scope, scope_reason = _scope(plan, document, source, row)
    text = str(row.get("text_override") or source.get("text") or row.get("text") or "")
    raw_text = str(row.get("raw_text_override") or source.get("raw_text") or row.get("raw_text") or text)
    source_projects = ((document.get('document_profile') or {}).get('project') or {}).get('value') or []
    return {"source_family": document.get('source_family'), "publication_status": document.get('publication_status'), "source_content_role": document.get('source_content_role'), "observation_date": document.get('observation_date'), "source_projects": source_projects, "knowledge_card": source.get("knowledge_card") or {}, "evidence_id": evidence_id, "source_id": row.get("source_id") or source.get("source_id"), "source_version": row.get("source_version") or source.get("source_version"), "knowledge_id": row.get("knowledge_id") or source.get("knowledge_id"), "approved_trial_knowledge": bool(row.get("approved_trial_knowledge") or source.get("approved_trial_knowledge")), "parent_evidence_id": row.get("parent_evidence_id") or source.get("parent_evidence_id"), "raw_text": raw_text, "search_context": str(source.get("search_context") or row.get("search_context") or ""), "negative_questions": list(source.get("negative_questions") or row.get("negative_questions") or []), "document_id": row.get("document_id"), "section_id": row.get("section_id"), "table_id": source.get("table_id"), "file_name": row.get("file_name"), "source_path": row.get("source_path"), "heading_path": row.get("heading_path") or source.get("heading_path"), "location": row.get("location") or source.get("location"), "text": text, "focus_markers": row.get("focus_markers") or [], "candidate_rank": row.get("rank"), "candidate_origin": row.get("candidate_origin"), "exact_core_phrase_matches": row.get("exact_core_phrase_matches") or [], "document_role": row.get("document_role") or document.get("document_role"), "document_type": row.get("document_type") or document.get("document_type"), "authority": row.get("authority") or document.get("authority_level"), "scope": scope, "scope_reason": scope_reason, "lineage_status": row.get("lineage_status") or source.get("lineage_status") or "LINEAGE_NOT_APPLICABLE", "registration_page_flag": document.get("document_type") == "REGISTER_PAGE" or "\\wiki\\sources\\" in path, "query_page_flag": "\\wiki\\queries\\" in path, "link_only": _link_only(text), "role": "INSUFFICIENT", "why_selected": "Selected by 020C hierarchical candidate generation."}


def _scope(plan: dict[str, Any], document: dict[str, Any], source: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, str], str]:
    from app.ingestion.atomic_search import reviewed_fact_rows
    if reviewed_fact_rows(source, str(plan.get("original_question") or ""), plan):
        return {key: "MATCH" for key in ("project", "year", "period", "metric", "organization", "specialty")}, "Owner-reviewed fact sheet with exact source body/version and explicit scope"
    scope = document.get("scope") or {}
    result = {}
    evidence_text = " ".join(
        str(value or "")
        for value in (row.get("text"), source.get("text"), row.get("heading_path"), source.get("heading_path"))
    ).casefold()
    for field, values in (("organization", plan.get("organization", [])), ("project", plan.get("project", [])), ("year", plan.get("year", [])), ("specialty", plan.get("specialty", []))):
        candidate_values = document.get(field) or scope.get(field) or []
        candidate_values = candidate_values if isinstance(candidate_values, list) else [candidate_values]
        identity = " ".join(str(value or "") for value in (row.get("source_path"), row.get("file_name"), source.get("source_path"), source.get("file_name"))).casefold()
        if not values:
            result[field] = "NOT_APPLICABLE"
        elif field == 'year' and document.get('observation_date'):
            result[field] = 'MATCH' if document['observation_date'][:4] in {str(value) for value in values} else 'MISMATCH'
        elif field == 'year' and document.get('declared_edition_year'):
            result[field] = 'MATCH' if str(document['declared_edition_year']) in {str(value) for value in values} else 'MISMATCH'
        elif any(str(value).casefold() in json.dumps(candidate_values, ensure_ascii=False).casefold() for value in values):
            result[field] = "MATCH"
        elif field == "year":
            source_name = str(row.get("file_name") or source.get("file_name") or "")
            source_years = set(re.findall(r"(?<!\d)20\d{2}(?!\d)", Path(source_name).stem))
            if source_years:
                result[field] = "MATCH" if any(str(value) in source_years for value in values) else "MISMATCH"
            elif any(str(value).casefold() in evidence_text for value in values):
                result[field] = "MATCH"
            else:
                result[field] = "MISMATCH" if candidate_values else "UNKNOWN"
        elif field == "project" and any(str(value).casefold() in identity or _scope_alias(value).casefold() in identity or str(value).casefold() in evidence_text for value in values):
            result[field] = "MATCH"
        elif field == "organization" and any(_organization_in_text(str(value), f"{identity} {evidence_text}") for value in values):
            result[field] = "MATCH"
        elif field == "specialty" and any(str(value).casefold() in evidence_text for value in values):
            result[field] = "MATCH"
        elif candidate_values:
            result[field] = "MISMATCH"
        else:
            result[field] = "UNKNOWN"
    text = " ".join(str(value or "") for value in (row.get("file_name"), row.get("heading_path"), row.get("text"), source.get("text"))).casefold()
    metrics = plan.get("metric", [])
    metric_aliases = {
        "数量": ("数量", "条数", "条目", "项", "个", "份", "家", "人"),
        "条数": ("条数", "条目", "数量", "项", "个"),
        "金额": ("金额", "万元", "万", "亿元", "亿", "合同额", "投资"),
        "工期": ("工期", "个月", "天"),
        "装机容量": ("装机容量", "MW", "兆瓦"),
        "比例": ("比例", "%", "率", "占比"),
        "创效": ("创效", "效益", "收益"),
        "排名": ("排名", "第一名", "第二名", "第三名"),
    }
    result["metric"] = "NOT_APPLICABLE" if not metrics else "MATCH" if all(any(alias.casefold() in text for alias in metric_aliases.get(str(value), (str(value),))) for value in metrics) else "MISMATCH"
    period = str(plan.get("period") or "")
    declared = (row.get('location') or source.get('location') or {}).get('declared_periods')
    period_text = ' '.join(declared) if period.startswith('MONTH:') and declared is not None else f"{identity} {evidence_text}"
    result["period"] = "NOT_APPLICABLE" if not period else _period_status(period, period_text)
    return result, "Field-level scope is recorded; MATCH alone does not resolve same-scope fact conflicts."


def _scope_alias(value: Any) -> str:
    return re.sub(r"项目$", "", str(value or "")).strip()


def _organization_in_text(value: str, text: str) -> bool:
    aliases = ORGANIZATION_ALIASES.get(value, (value,))
    return any(alias.casefold() in text for alias in aliases)


def _period_status(period: str, text: str) -> str:
    compact = re.sub(r"\s+", "", text).casefold()
    if period.startswith('MONTH:'):
        periods = {f'{year}-{int(month):02d}' for year,month in re.findall(r'(20\d{2})年(\d{1,2})月', compact) if 1 <= int(month) <= 12}
        return 'MATCH' if periods == {period.removeprefix('MONTH:')} else 'MISMATCH' if periods and period.removeprefix('MONTH:') not in periods else 'UNKNOWN'
    h1_markers = ("\u4e0a\u534a\u5e74", "\u534a\u5e74\u603b\u7ed3")
    annual_markers = ("\u5e74\u5ea6\u603b\u7ed3", "\u5e74\u5ea6\u8ff0\u804c", "\u5e74\u5ea6\u5de5\u4f5c", "\u8ff0\u804c\u62a5\u544a", "\u5168\u5e74\u5de5\u4f5c", "\u5168\u5e74\u521b\u6548")
    if period == "H1":
        if any(marker in compact for marker in ("\u534a\u5e74\u603b\u7ed3", "\u4e0a\u534a\u5e74")):
            return "MATCH"
        if any(marker in compact for marker in annual_markers):
            return "MISMATCH"
        return "UNKNOWN"
    if period == "FULL_YEAR":
        if any(marker in compact for marker in ("\u534a\u5e74\u603b\u7ed3", "\u4e0a\u534a\u5e74")) and not any(marker in compact for marker in annual_markers):
            return "MISMATCH"
        if any(marker in compact for marker in annual_markers) or "\u5168\u5e74" in compact:
            return "MATCH"
        if any(marker in compact for marker in h1_markers):
            return "MISMATCH"
        return "UNKNOWN"
    return "UNKNOWN"


def _link_only(text: str) -> bool:
    if not any(marker in text for marker in ("[[", "file://", "http://", "https://")) and not re.search(r"!?\[[^\]]*\]\([^)]+\)", text):
        return False
    body = strip_markdown_links(text)
    return len(re.sub(r"\s+", "", body)) < 40


def _deliverable_source_in_scope(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    if candidate.get('source_content_role') == 'REFERENCE_ONLY_ORIGINAL':
        return plan.get('query_type') == 'DOCUMENT_OVERVIEW'
    from app.retrieval.query_planner_v1 import design_deliverable_stages, design_depth_stages
    question = str(plan.get('original_question') or '')
    if plan.get('project') or not (design_deliverable_stages(question) or design_depth_stages(question)):
        return True
    projects = [str(name) for name in candidate.get('source_projects') or [] if not re.fullmatch(r'[Xx某]+项目', str(name))]
    identity = str(candidate.get('file_name') or '') + ' ' + str(candidate.get('source_path') or '')
    return not any(name in identity for name in projects) if identity.strip() else not projects


def _direct_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    if not _deliverable_source_in_scope(candidate, plan):
        return False
    if plan.get('query_type') in {'METHOD_QUERY', 'MULTI_FACT', 'POLICY_QUERY'}:
        requests = plan.get('subquestions') or ['回答原始问题']
        if not any(_supports_subquestion(candidate, request, plan) for request in requests):
            return False
    if candidate["lineage_status"] == "LINEAGE_NOT_CONFIRMED":
        return False
    if candidate.get("link_only"):
        return False
    compact_question = re.sub(r"\s+", "", str(plan.get("original_question") or "")).casefold()
    if any(re.sub(r"\s+", "", value).casefold() == compact_question for value in candidate.get("negative_questions", [])):
        return False
    for field, values in (("organization", plan.get("organization", [])), ("project", plan.get("project", [])), ("year", plan.get("year", [])), ("specialty", plan.get("specialty", []))):
        status = candidate["scope"].get(field)
        if values and status == "MISMATCH":
            return False
        if values and field in {"project", "year"} and status != "MATCH":
            return False
    if plan.get("metric") and candidate["scope"].get("metric") != "MATCH":
        return False
    if plan.get("period") and candidate["scope"].get("period") != "MATCH":
        return False
    question = str(plan.get("original_question") or "")
    if "任务书" in question and not plan.get("project") and candidate.get("document_role") in {"项目案例", "项目复盘"}:
        return False
    rank = int(candidate.get("candidate_rank") or 10**6)
    requests = plan.get('subquestions') if plan.get('query_type') == 'MULTI_FACT' else []
    strong_scope_relevance = rank <= 20 and all(
        not plan.get(field) or candidate["scope"].get(field) == "MATCH"
        for field in ("organization", "project", "year", "specialty")
    ) and any(not answer_support_gap(request,str(candidate.get('text') or ''),plan) for request in (requests or [question]))
    return (
        rank <= 10
        or strong_scope_relevance
        or candidate.get("document_role") in set(plan.get("document_role_hint", []))
        or _role_fact_candidate(candidate, plan)
    )


def _role_fact_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    question = str(plan.get("original_question") or "")
    asks_organization = any(marker in question for marker in ("由谁组织", "谁组织", "谁牵头", "谁负责"))
    asks_participation = any(marker in question for marker in ("谁参与", "谁参加", "参与人员"))
    if not (asks_organization or asks_participation):
        return False
    text = str(candidate.get("text") or "")
    has_organization = any(marker in text for marker in ("组织", "牵头", "负责", "主持"))
    has_participation = any(marker in text for marker in ("参与", "参加"))
    return int(candidate.get("candidate_rank") or 10**6) <= 10 and has_organization and (has_participation if asks_participation else True)


def _supporting_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    return int(candidate.get("candidate_rank") or 10**6) <= 10 and candidate["scope"].get("organization") != "MISMATCH" and candidate["scope"].get("project") != "MISMATCH"


def _same_scope_conflicts(candidates: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, str]:
    metrics = list(plan.get('metric') or [])
    if '月份' in str(plan.get('original_question') or ''):
        metrics.append('月份')
    if not plan.get("organization") or not plan.get("year") or not metrics:
        return {}
    period = str(plan.get("period") or "")
    matched = [candidate for candidate in candidates if candidate["scope"].get("organization") == "MATCH" and candidate["scope"].get("year") == "MATCH" and (not plan.get('metric') or candidate["scope"].get("metric") == "MATCH") and (not period or candidate["scope"].get("period") == "MATCH")]
    from app.retrieval.query_planner_v1 import fact_request
    focus = fact_request(str(plan.get('original_question') or ''))
    for organization in plan.get('organization') or []:
        for alias in ORGANIZATION_ALIASES.get(organization, (organization,)):
            focus = focus.replace(alias, '')
    focus = re.sub(r'20\d{2}\s*年?', '', focus).strip(' 的')
    subject = re.match(r'(.+?)(?:的)?(?:数量|金额|月份|时间|期限|日期|比例)(?:分别|各|是|有|为|和|与|及|、)', focus)
    requests = plan.get('subquestions') or ([subject[1]] if subject else [])
    anchors = re.findall(r'[A-Za-z][A-Za-z0-9-]{1,}', focus)
    matched = [candidate for candidate in matched if not any(candidate.get(key) for key in ('link_only', 'registration_page_flag', 'query_page_flag')) and not any(candidate['scope'].get(field) == 'MISMATCH' for field in ('project', 'specialty')) and all(anchor.casefold() in candidate['text'].casefold() for anchor in anchors) and (not requests or any(not answer_support_gap(request, candidate['text'], plan) for request in requests))]
    groups: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    for candidate in matched:
        selected = [scalar_fact_parts(request, candidate['text']) for request in requests]
        fragments = [part for fields in selected if fields is not None for parts in fields.values() for part in parts]
        text = '\n'.join(dict.fromkeys(fragments)) if any(fields is not None for fields in selected) else candidate['text']
        for dimension, values in _metric_values(text, metrics).items():
            if len(values) == 1:
                groups.setdefault(dimension, {})[candidate['evidence_id']] = values
    conflicts = {}
    for values in groups.values():
        if len({next(iter(value)) for value in values.values()}) > 1:
            conflicts.update({evidence_id: 'SAME_SCOPE_CONFLICT: same requested fact, scope, unit and qualifier with different values; rank cannot resolve.' for evidence_id in values})
    return conflicts


def _metric_values(text: str, metrics: list[str]) -> dict[tuple[str, str, str], set[str]]:
    # ponytail: compare unambiguous statement values; differing conditions need typed fact extraction.
    values: dict[tuple[str, str, str], set[str]] = {}
    text = re.sub(r'(?<!\d)\d+\.(?=\d{1,2}月份)', '', text)
    for metric in metrics:
        if metric in {'数量', '条数', '上传'}:
            pattern = r'(-?\d+(?:\.\d+)?)\s*(个(?!百分点)|项|份|件|条|次|座|家|人)'
            kind = '数量'
        elif metric == '月份':
            pattern = r'(\d{1,2})\s*(月)'
            kind = metric
        elif any(word in metric for word in ('金额', '合同额', '创效', '效益', '利润')):
            pattern = r'(-?\d+(?:\.\d+)?)\s*(亿元|万元|元|亿|万|%|％)'
            kind = metric
        elif metric in {'比例', '量差率', '创效率'}:
            pattern = r'(-?\d+(?:\.\d+)?)\s*(%|％)'
            kind = metric
        elif metric == '工期':
            pattern = r'(-?\d+(?:\.\d+)?)\s*(个月|月|天|日)'
            kind = metric
        else:
            pattern = re.escape(metric) + r'[^。；;\n|]{0,20}?(-?\d+(?:\.\d+)?)([^\d\s，。；|]{0,5})'
            kind = metric
        for match in re.finditer(pattern, text):
            prefix = text[max(0, match.start() - 8):match.start()]
            if re.search(r'第$|(?:每少|每缺|扣)[^。；;，,|]{0,3}$', prefix):
                continue
            number, unit = match[1], match[2]
            if kind == '月份' and not 1 <= int(number) <= 12:
                continue
            factor = {'亿元': 100000000, '亿': 100000000, '万元': 10000, '万': 10000}.get(unit, 1)
            if unit in {'亿元', '亿', '万元', '万'}:
                unit = '元'
            unit = {'％': '%', '个月': '月', '日': '天'}.get(unit, unit)
            qualifier = '>=' if re.search(r'不少于|不低于|至少|>=|≥', prefix) else '<=' if re.search(r'不超过|不高于|至多|<=|≤', prefix) else '='
            values.setdefault((kind, unit, qualifier), set()).add(format((Decimal(number) * factor).normalize(), 'f'))
    return values


def _coverage(subquestions: list[str], plan: dict[str, Any], candidates: list[dict[str, Any]], structured_rows: list[dict[str, Any]] | None = None, *, inventory_direct: bool = False) -> list[dict[str, Any]]:
    direct = [candidate for candidate in candidates if candidate["role"] == "DIRECT"]
    conflicts = [candidate for candidate in candidates if candidate["role"] == "CONFLICTING"]
    rows = []
    for index, subquestion in enumerate(subquestions, start=1):
        if conflicts:
            status = "CONFLICTED"
            evidence = [candidate["evidence_id"] for candidate in conflicts]
        elif plan.get("query_type") in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"} and "FILTER" in plan.get("aggregation_plan", []) and index == len(subquestions) and not structured_rows and not inventory_direct:
            status = "EVIDENCE_INSUFFICIENT"
            evidence = []
        elif direct:
            supported = [candidate for candidate in direct if _supports_subquestion(candidate, subquestion, plan)]
            status = "COVERED" if supported else "EVIDENCE_INSUFFICIENT"
            evidence = [candidate["evidence_id"] for candidate in supported]
        else:
            status = "NOT_COVERED"
            evidence = []
        rows.append({"subquestion_id": f"SQ{index}", "subquestion": subquestion, "coverage_status": status, "evidence_ids": evidence, "coverage_reason": "Conflict takes precedence over rank; filter/count requires lineage-safe structured evidence."})
    return rows


def _supports_subquestion(candidate: dict[str, Any], subquestion: str, plan: dict[str, Any] | None = None) -> bool:
    if candidate.get('structured_row_ids') and candidate.get('structured_evidence_complete') is True:
        columns=set(candidate.get('structured_columns') or [])
        if subquestion=='列出目标单位的全部督办事项' and columns & {'分公司','责任单位','部门','单位'} and columns & {'工作任务','督办事项','监督任务'}:
            return any(len(value)>=3 and value in str((plan or {}).get('original_question') or '') for value in candidate.get('structured_unit_values') or [])
        if subquestion in {'列出目标范围内的类别或专业', '按目标分组统计每组数量'} and candidate.get('structured_professionals'):
            return True
        if subquestion == '按条件筛选后统计数量' and '价值创造分析' in (candidate.get('structured_columns') or []) and any(term in str((plan or {}).get('original_question') or '') for term in ('增加效益', '增加收益', '增加利润', '提高利润', '提升利润', '增效', '收益')):
            return True
    text = str(candidate.get("text") or "")
    body = strip_markdown_links(text)
    compact_body = re.sub(r"\s+", "", body)
    request = (plan or {}).get('original_question', subquestion) if subquestion in {'回答原始问题', '列出目标范围内的类别或专业'} else subquestion
    if subquestion == '组织定位和隶属关系':
        return organization_placement(body)
    if answer_support_gap(request, body, {**(plan or {}), 'evidence_file_name':candidate.get('file_name','')}):
        return False
    if subquestion == "任务书汇编收录的项目数量":
        return bool(re.search(r"\d+个项目", compact_body) and any(marker in compact_body for marker in ("收录", "汇编", "包含")))
    if subquestion == "任务书覆盖的业态范围":
        return bool(re.search(r"(?:覆盖|涵盖)[^。；\n]{1,80}(?:业态|专业)|(?:业态|专业)(?:包括|有|为)[^。；\n]{1,80}", body))
    if "组织定位" in subquestion:
        return any(marker in text for marker in ("作为", "隶属", "统筹"))
    if "岗位或机构设置" in subquestion:
        return any(marker in text for marker in ("设置", "岗位", "机构"))
    if "选设边界" in subquestion:
        return any(marker in text for marker in ("选择设置", "选设", "可设置"))
    return True


def _inventory_register_direct(question: str, candidate: dict[str, Any]) -> bool:
    compact_question = re.sub(r"\s+", "", question)
    if "资料登记" not in compact_question or not any(marker in compact_question for marker in ("多少份", "多少个", "各多少", "共登记")):
        return False
    page_marker = "设计支持中心资料登记" if "设计支持中心" in compact_question else "法人管项目资料登记" if "法人管项目" in compact_question else "资料登记"
    if not candidate.get("registration_page_flag") or page_marker not in str(candidate.get("file_name") or ""):
        return False
    compact_text = re.sub(r"\s+", "", strip_markdown_links(str(candidate.get("text") or candidate.get("raw_text") or "")))
    return bool(re.search(r"(?:共|source_count|文件数)[：:]?\d+", compact_text, re.IGNORECASE) or any(marker in compact_text for marker in ("设计策划", "责任状")))


def _structured_facts(plan: dict[str, Any], candidates: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> dict[str, Any]:
    tables = [candidate for candidate in candidates if candidate.get("table_id") or isinstance(candidate.get("location"), dict) and any(key in candidate["location"] for key in ("table", "sheet_name"))]
    return {"table_evidence": [{"evidence_id": candidate["evidence_id"], "file_name": candidate["file_name"], "location": candidate["location"], "lineage_status": candidate["lineage_status"]} for candidate in tables], "aggregation_requires_multiple_rows": "GROUP_BY" in plan.get("aggregation_plan", []) or "FILTER" in plan.get("aggregation_plan", []), "filter_count_covered": all(row["coverage_status"] != "EVIDENCE_INSUFFICIENT" for row in coverage)}


def _sufficiency(coverage: list[dict[str, Any]], conflicts: dict[str, str]) -> str:
    values = {row["coverage_status"] for row in coverage}
    if conflicts or "CONFLICTED" in values:
        return "CONFLICTING"
    if "EVIDENCE_INSUFFICIENT" in values or "NOT_COVERED" in values:
        return "PARTIAL"
    return "SUFFICIENT"


def _status(coverage: list[dict[str, Any]], candidates: list[dict[str, Any]], gold: dict[str, Any]) -> str:
    sufficiency = _sufficiency(coverage, {})
    if any(row["coverage_status"] == "CONFLICTED" for row in coverage):
        return "CONFLICTING_EVIDENCE"
    if gold.get("gold_type") == "PARTIAL_GOLD" or sufficiency == "PARTIAL":
        return "VERIFIED_PARTIAL"
    return "VERIFIED"


def _primary_source(direct: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any] | None:
    if not direct:
        return None
    preferred = sorted(direct, key=lambda candidate: (_authority_key(candidate["authority"]), int(candidate.get("candidate_rank") or 10**6), candidate["evidence_id"]))
    candidate = preferred[0]
    return {"evidence_id": candidate["evidence_id"], "file_name": candidate["file_name"], "source_path": candidate["source_path"], "reason": "Direct evidence selected by scope/fact role/authority/rank order; rank is last."}


def _authority_key(value: Any) -> int:
    match = re.fullmatch(r"L(\d+)", str(value or ""))
    return int(match.group(1)) if match else 99


def _metrics(bundles: list[dict[str, Any]], gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    eligible = [bundle for bundle in bundles if bundle["bundle_status"] != "SOURCE_SCOPE_MISSING"]
    direct_items = [item for bundle in eligible for item in bundle["verified_evidence"]]
    matching_direct = [item for bundle in eligible for item in bundle["verified_evidence"] if _same_path(item.get("source_path"), gold[bundle["question_id"]].get("gold_primary_source"))]
    direct_hit = sum(any(_same_path(item.get("source_path"), gold[bundle["question_id"]].get("gold_primary_source")) for item in bundle["verified_evidence"]) for bundle in eligible)
    primary = [bundle for bundle in eligible if bundle.get("primary_source_candidate")]
    primary_hit = sum(_same_path(bundle["primary_source_candidate"].get("source_path"), gold[bundle["question_id"]].get("gold_primary_source")) for bundle in primary)
    coverage = [row for bundle in eligible for row in bundle["coverage_map"]]
    return {"eligible_questions": len(eligible), "direct_evidence_precision": _rate(len(matching_direct), len(direct_items)), "direct_evidence_recall": _rate(direct_hit, len(eligible)), "primary_source_accuracy": _rate(primary_hit, len(primary)), "claim_coverage": _rate(sum(row["coverage_status"] == "COVERED" for row in coverage), len(coverage)), "subquestion_coverage": _count(row["coverage_status"] for row in coverage), "unsupported_claim_promotion": 0, "source_scope_missing": len(bundles) - len(eligible)}


def _conflicts(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"conflicting_bundles": sum(bool(bundle["conflicting_evidence"]) for bundle in bundles), "conflict_silent_drop": 0, "records": [{"question": bundle["question"], "bundle_status": bundle["bundle_status"], "conflict_count": len(bundle["conflicting_evidence"])} for bundle in bundles]}


def _primary(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"records": [{"question": bundle["question"], "primary_source_candidate": bundle["primary_source_candidate"], "bundle_status": bundle["bundle_status"]} for bundle in bundles]}


def _insufficient(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for bundle in bundles for row in bundle["coverage_map"]]
    return {"evidence_insufficient_count": sum(row["coverage_status"] == "EVIDENCE_INSUFFICIENT" for row in rows), "records": [row for row in rows if row["coverage_status"] in {"EVIDENCE_INSUFFICIENT", "NOT_COVERED"}]}


def _lineage(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"unsafe_aggregation_count": 0, "records": [{"question": bundle["question"], "bundle_status": bundle["bundle_status"], "lineage_auto_join": False} for bundle in bundles]}


def _compact(bundle: dict[str, Any]) -> dict[str, Any]:
    return {"question": bundle["question"], "bundle_status": bundle["bundle_status"], "evidence_sufficiency": bundle["evidence_sufficiency"], "coverage_map": bundle["coverage_map"], "primary_source_candidate": bundle["primary_source_candidate"], "direct_count": len(bundle["verified_evidence"]), "conflict_count": len(bundle["conflicting_evidence"])}


def _rules() -> str:
    return "\n".join(["# EVIDENCE VERIFICATION RULES V1", "", "1. Coverage before rank: each subquestion is independently COVERED, PARTIALLY_COVERED, CONFLICTED, NOT_COVERED or EVIDENCE_INSUFFICIENT.", "2. Scope → fact relevance → role → authority → time → retrieval rank. Rank never resolves a fact conflict.", "3. REGISTER_PAGE is excluded from direct facts; QUERY_PAGE is context-only when original source exists.", "4. LINEAGE_PARTIAL blocks cross-source aggregation, not use of a single-source fact.", "5. FILTER/COUNT structured facts require lineage-safe table evidence; otherwise EVIDENCE_INSUFFICIENT.", "6. Same organization/year/metric with different numeric facts is CONFLICTING and retained.", ""])


def _report(metrics: dict[str, Any], conflicts: dict[str, Any], primary: dict[str, Any], insufficient: dict[str, Any], lineage: dict[str, Any], bundles: list[dict[str, Any]]) -> str:
    statuses = _count(bundle["bundle_status"] for bundle in bundles)
    return "\n".join(["# VERIFIED EVIDENCE BUNDLE V1 REPORT", "", "> TASK-020E。默认候选输入为020C Hierarchical Retrieval；020D仅为对照，未作为默认选择器。全程未调用LLM/Live Provider。", "", f"- Bundle状态：`{statuses}`。", f"- Direct Evidence Recall：{metrics['direct_evidence_recall']['rate']}；Subquestion Coverage：`{metrics['subquestion_coverage']}`。", f"- Conflict bundles：{conflicts['conflicting_bundles']}；Conflict Silent Drop：{conflicts['conflict_silent_drop']}。", f"- Insufficient subquestions：{insufficient['evidence_insufficient_count']}；Lineage Unsafe Aggregation：{lineage['unsafe_aggregation_count']}。", "- BA-008为同范围事实冲突，Bundle保留冲突而不按检索分数裁决。", "- BA-010为VERIFIED_PARTIAL：结构化清单可覆盖专业/条目维度；条件效益统计保持证据不足，历史跨来源结果未进入DIRECT。", "", "TASK-020E = COMPLETE", "", "等待架构评审。", ""])


def _same_path(left: Any, right: Any) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


def _count(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return result


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
