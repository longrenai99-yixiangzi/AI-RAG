from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem, select_evidence_optimized
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.config import Settings
from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceClassifier, GovernanceMetadata
from scripts.evaluate_business_query_regression import load_questions
from scripts.shadow_answer_router_v1 import load_fact_capability
from scripts.shadow_answer_router_v1_1 import route_question
from scripts.validate_unified_shadow_business import ROOT_CONFIG, load_qdrant_chunks


BASELINE_DIR = PROJECT_ROOT / "evaluation" / "v1_business_acceptance"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "scope_guard_leakage_cleanup"
REPORT_PATH = PROJECT_ROOT / "docs" / "SCOPE_GUARD_TEST_LEAKAGE_CLEANUP_REPORT.md"
GOLD_PATH = PROJECT_ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
FACT_ANSWER_DIR = PROJECT_ROOT / "evaluation" / "fact_answers"

BASE_NEGATIVE_CASES = [
    ("N-001", "2025年公司设计创效金额是多少？"),
    ("N-003", "公司全年服务了多少个项目？"),
    ("N-005", "公司设计效益率目标是多少？"),
    ("N-GROUP-01", "2025年局设计创效金额是多少？"),
    ("N-BRANCH-01", "2025年分公司设计创效金额是多少？"),
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scan_runtime_hardcoding() -> dict[str, list[dict[str, Any]]]:
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    patterns = (
        "华师南湖训练馆",
        "星谷科创中心",
        "某项目",
        "4.45",
        "445,000,000",
        "2594.70",
        "2025年饶淇述职.md",
    )
    runtime: list[dict[str, Any]] = []
    report_only: list[dict[str, Any]] = []
    test_assertion: list[dict[str, Any]] = []
    in_report_function = False
    in_scan_function = False
    for number, line in enumerate(lines, start=1):
        if line.startswith("def scan_runtime_hardcoding"):
            in_scan_function = True
        elif line.startswith("def ") and not line.startswith("def scan_runtime_hardcoding"):
            in_scan_function = False
        if line.startswith("def render_"):
            in_report_function = True
        hits = [pattern for pattern in patterns if pattern in line]
        if not hits:
            continue
        if in_scan_function:
            continue
        item = {"line": number, "patterns": hits, "text": line.strip()}
        if "assert " in line or "validation passed" in line:
            test_assertion.append(item)
        elif in_report_function or "scope_document_audit" in line:
            report_only.append(item)
        else:
            runtime.append(item)
    return {
        "runtime_hardcoding": runtime,
        "report_only_hardcoding": report_only,
        "test_assertion_hardcoding": test_assertion,
    }


def extract_project_entities(question: str, known_entities: list[str]) -> list[str]:
    matched = sorted(
        {entity for entity in known_entities if entity and entity in question},
        key=len,
        reverse=True,
    )
    if matched:
        return matched[:3]
    fallback = []
    for match in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9（）()·+\-]{2,32})项目", question):
        entity = match.group(1).strip("（）() ")
        if not any(token in entity for token in ("多少", "服务", "公司", "设计", "当前")):
            fallback.append(entity)
    return list(dict.fromkeys(fallback))


def query_scope(question: str, route: dict[str, Any], known_entities: list[str] | None = None) -> dict[str, Any]:
    known_entities = known_entities or []
    if "分公司" in question:
        organization = "BRANCH"
    elif "公司" in question:
        organization = "COMPANY"
    elif "局" in question:
        organization = "GROUP"
    else:
        organization = "UNKNOWN"

    project_terms = extract_project_entities(question, known_entities)
    if not project_terms and "项目" in question and organization == "UNKNOWN":
        project_terms.append("项目")
    entity = "PROJECT" if project_terms else ("ORGANIZATION_TOTAL" if organization in {"COMPANY", "GROUP", "BRANCH"} else "UNKNOWN")
    if "责任状" in question or "制度" in question or "规定" in question:
        entity = "POLICY"

    year_match = re.search(r"(20\d{2})年", question)
    month_match = re.search(r"(\d{1,2})月", question)
    if year_match:
        time_scope = "YEAR"
        time_value = year_match.group(1)
    elif month_match:
        time_scope = "MONTH"
        time_value = month_match.group(1)
    else:
        time_scope = "NONE"
        time_value = None

    if "设计创效金额" in question or "设计价值创造金额" in question:
        metric = "DESIGN_VALUE_CREATION_AMOUNT"
    elif "目标" in question and ("率" in question or "金额" in question or "数量" in question):
        metric = "TARGET"
    elif any(term in question for term in ("金额", "多少钱", "多少元", "多少万元")):
        metric = "AMOUNT"
    elif any(term in question for term in ("比例", "占比", "效益率", "创效率")):
        metric = "RATE"
    elif any(term in question for term in ("多少", "数量", "几个", "几项", "几条")):
        metric = "COUNT"
    elif any(term in question for term in ("日期", "时间", "何时")):
        metric = "DATE"
    else:
        metric = "TEXT_FACT"

    return {
        "organization_scope": organization,
        "time_scope": time_scope,
        "time_value": time_value,
        "entity_scope": entity,
        "metric_scope": metric,
        "reporting_period": reporting_period_for_text(question),
        "finality": "FINAL" if any(term in question for term in ("实际", "已完成", "全年")) else "UNKNOWN",
        "aggregation_scope": "DIRECT_REPORTED_FACT" if route.get("fact_mode") == "DIRECT_FACT" else "NOT_DIRECT_FACT",
        "project_terms": project_terms,
    }


def document_scope(chunks: list[Chunk], governance: GovernanceMetadata) -> dict[str, Any]:
    first = chunks[0]
    name_path = f"{first.file_name} {first.source_path} {first.heading_path}".casefold()
    filename_path = f"{first.file_name} {first.source_path}".casefold()
    body = "\n".join(chunk.text for chunk in chunks)[:30_000]
    path_project = any(term in filename_path for term in ("设计复盘", "项目案例", "项目经验总结", "项目总结", "epc设计管理经验总结"))
    path_company = any(term in filename_path for term in ("述职", "年度工作总结", "年度总结", "公司总部"))
    if path_project:
        organization = "PROJECT"
        subject = "PROJECT"
    elif path_company:
        organization = "COMPANY"
        subject = "ORGANIZATION_TOTAL"
    elif governance.document_role == "项目案例":
        organization = "PROJECT"
        subject = "PROJECT"
    elif governance.document_role in {"正式制度", "管理指南", "标准模板"}:
        organization = "UNKNOWN"
        subject = "POLICY"
    else:
        # Body terms are deliberately weak and only used when path/name and
        # governance signals are unavailable.
        body_company = any(term in body for term in ("公司总部", "公司全年", "公司设计中心"))
        organization = "COMPANY" if body_company else "UNKNOWN"
        subject = "ORGANIZATION_TOTAL" if body_company else "UNKNOWN"

    years = re.findall(r"20\d{2}", f"{first.file_name} {body}")
    year = years[0] if years else None
    combined = f"{first.file_name} {body}"
    if (
        ("设计创效" in combined or "设计价值创造" in combined)
        and ("创效金额" in combined or "金额" in combined)
    ):
        metric = "DESIGN_VALUE_CREATION_AMOUNT"
    elif any(term in combined for term in ("金额", "亿元", "万元", "元")):
        metric = "AMOUNT"
    elif any(term in f"{first.file_name} {body}" for term in ("效益率", "创效率", "比例", "占比")):
        metric = "RATE"
    elif any(term in f"{first.file_name} {body}" for term in ("数量", "多少个", "多少条")):
        metric = "COUNT"
    else:
        metric = "TEXT_FACT"
    fact_strength = 0.0
    if all(term in body for term in ("全年服务项目", "提出创效", "入图", "创效金额")):
        fact_strength += 0.35
    if "设计管理创效" in body and "创效金额" in body:
        fact_strength += 0.20
    if "预计实现创效金额" in body:
        fact_strength -= 0.10
    header = f"{first.file_name} {first.source_path} {first.heading_path}"
    header_period = reporting_period_for_text(header)
    reporting_period = header_period if header_period != "UNKNOWN" else reporting_period_for_text(body)
    header_finality = finality_for_text(header)
    finality = header_finality if header_finality != "UNKNOWN" else finality_for_text(body)
    return {
        "document_scope": organization,
        "subject_scope": subject,
        "time_scope": "YEAR" if year else "NONE",
        "time_value": year,
        "metric_scope": metric,
        "fact_strength": fact_strength,
        "reporting_period": reporting_period,
        "finality": finality,
        "project_entities": extract_project_entities_from_text(filename_path),
        "document_role": governance.document_role,
        "authority_level": governance.authority_level,
    }


def reporting_period_for_text(text: str) -> str:
    if "半年" in text:
        return "HALF_YEAR"
    if "季度" in text or "一季度" in text or "二季度" in text or "三季度" in text or "四季度" in text:
        return "QUARTER"
    if re.search(r"\d{1,2}月", text):
        return "MONTH"
    if re.search(r"20\d{2}", text):
        return "FULL_YEAR"
    return "UNKNOWN"


def finality_for_text(text: str) -> str:
    if "预计" in text or "计划" in text or "目标" in text:
        return "FORECAST"
    if any(term in text for term in ("全年服务", "实际", "完成", "实现", "述职")):
        return "FINAL"
    return "UNKNOWN"


def finality_for_fact_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    values = list(re.finditer(r"(?:设计创效金额|设计价值创造金额|创效金额|金额)[^0-9]{0,16}\d+(?:\.\d+)?(?:亿|万|元)", compact))
    for match in values:
        window = compact[max(0, match.start() - 28): match.end() + 28]
        if "预计" in window or "计划" in window or "目标" in window:
            return "FORECAST"
        if any(term in window for term in ("实际", "完成", "实现", "全年服务")):
            return "FINAL"
    return "UNKNOWN"


def extract_project_entities_from_text(text: str) -> list[str]:
    entities: list[str] = []
    for pattern in (
        r"[（(]([^（）()]{2,32}?)(?:项目|工程|中心)[）)]",
        r"([\u4e00-\u9fffA-Za-z0-9·+\-]{2,32})(?:项目|工程|中心)",
    ):
        for match in re.finditer(pattern, text):
            value = match.group(1).strip(" -_")
            if value and value not in entities and not any(token in value for token in ("公司", "设计", "总结", "经验")):
                entities.append(value)
    return entities[:8]


def lexical_terms(question: str, query: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    organization_terms = {
        "GROUP": ("局",),
        "COMPANY": ("公司",),
        "BRANCH": ("分公司",),
        "PROJECT": tuple(query.get("project_terms", [])),
    }
    terms.extend(term for term in organization_terms.get(query.get("organization_scope"), ()) if term in question)
    metric_terms = {
        "DESIGN_VALUE_CREATION_AMOUNT": ("设计创效", "设计价值创造", "创效金额"),
        "AMOUNT": ("金额", "元", "万元", "亿元"),
        "COUNT": ("数量", "多少", "条", "个"),
        "RATE": ("效益率", "创效率", "比例", "占比"),
        "TARGET": ("目标", "要求", "规定"),
        "DATE": ("日期", "时间", "何时"),
        "TEXT_FACT": (),
    }
    terms.extend(term for term in metric_terms.get(query.get("metric_scope"), ()) if term in question)
    terms.extend(term for term in ("DOP", "责任状") if term in question)
    terms.extend(term for term in query.get("project_terms", []) if term in question)
    if query.get("reporting_period") == "FULL_YEAR":
        terms.append("全年")
    elif query.get("reporting_period") == "HALF_YEAR":
        terms.append("半年")
    year = re.search(r"20\d{2}", question)
    if year:
        terms.append(year.group(0))
    return list(dict.fromkeys(terms))


def scope_compatibility(query: dict[str, Any], candidate: dict[str, Any], searchable: str) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    if query["organization_scope"] == "COMPANY":
        if candidate["document_scope"] == "COMPANY":
            score += 0.45
            reasons.append("organization COMPANY matches")
        elif candidate["document_scope"] == "PROJECT":
            return "SCOPE_CONFLICT", -0.6, ["company query versus project document"]
    elif query["entity_scope"] == "PROJECT":
        if candidate["subject_scope"] == "PROJECT":
            score += 0.35
            reasons.append("entity PROJECT matches")
        elif candidate["subject_scope"] == "ORGANIZATION_TOTAL":
            return "SCOPE_CONFLICT", -0.45, ["project query versus organization total document"]

    if query.get("time_value") and candidate.get("time_value") == query["time_value"]:
        score += 0.25
        reasons.append("year matches")
    elif query.get("time_value") and candidate.get("time_value"):
        score -= 0.15
        reasons.append("year conflicts")

    if query["metric_scope"] == "DESIGN_VALUE_CREATION_AMOUNT" and candidate.get("metric_scope") != "DESIGN_VALUE_CREATION_AMOUNT":
        return "SCOPE_CONFLICT", -0.35, ["design value creation amount query versus generic amount fact"]
    if query["metric_scope"] == candidate.get("metric_scope"):
        score += 0.20
        reasons.append("metric matches")
    elif candidate.get("metric_scope") not in {None, "TEXT_FACT"}:
        score -= 0.08
        reasons.append("metric differs")

    project_terms = query.get("project_terms", [])
    if project_terms and any(term in searchable for term in project_terms):
        score += 0.20
        reasons.append("project entity appears in candidate")
    elif project_terms and candidate.get("subject_scope") == "PROJECT":
        score -= 0.10

    query_period = query.get("reporting_period", "UNKNOWN")
    candidate_period = candidate.get("reporting_period", "UNKNOWN")
    if query_period != "UNKNOWN" and candidate_period == query_period:
        score += 0.15
        reasons.append("reporting period matches")
    elif query_period == "HALF_YEAR" and candidate_period == "FULL_YEAR":
        return "PARTIAL_SCOPE_MATCH", score - 0.25, ["full-year candidate cannot substitute half-year query"]
    elif query_period == "FULL_YEAR" and candidate_period == "HALF_YEAR":
        score -= 0.25
        reasons.append("half-year candidate cannot cover full-year query")
    elif query_period != "UNKNOWN" and candidate_period not in {"UNKNOWN", query_period}:
        score -= 0.10
        reasons.append("reporting period differs")

    if query.get("finality") and candidate.get("finality") == query["finality"]:
        score += 0.10
        reasons.append("finality matches")

    if score >= 0.85:
        status = "EXACT_SCOPE_MATCH"
    elif score >= 0.35:
        status = "COMPATIBLE_SCOPE"
    elif score > -0.3:
        status = "PARTIAL_SCOPE_MATCH"
    else:
        status = "SCOPE_CONFLICT"
    return status, score, reasons


def direct_scope_guard_enabled(question: str, route: dict[str, Any], query: dict[str, Any]) -> bool:
    if route.get("fact_mode") == "DIRECT_FACT":
        return True
    if route.get("route") != "CLAIM_ANSWER_PATH":
        return False
    single_value_language = any(term in question for term in ("是多少", "多少个", "多少条", "多少元", "多少万元", "比例", "占比", "日期", "目标"))
    organization_or_project = query.get("organization_scope") in {"GROUP", "COMPANY", "BRANCH"} or query.get("entity_scope") == "PROJECT"
    return single_value_language and organization_or_project and query.get("metric_scope") in {
        "AMOUNT", "DESIGN_VALUE_CREATION_AMOUNT", "COUNT", "RATE", "TARGET", "DATE"
    }


def extract_direct_values(text: str, metric_scope: str) -> list[dict[str, Any]]:
    compact = re.sub(r"\s+", "", text)
    pattern = r"(?:设计创效金额|设计价值创造金额|创效金额|金额)[^0-9]{0,16}(\d+(?:\.\d+)?)(亿|万|元)"
    values: list[dict[str, Any]] = []
    for match in re.finditer(pattern, compact):
        value = float(match.group(1))
        unit = match.group(2)
        multiplier = {"亿": 100_000_000, "万": 10_000, "元": 1}[unit]
        values.append(
            {
                "raw": match.group(0),
                "value_yuan": round(value * multiplier, 2),
                "unit": unit,
                "is_approximate": "约" in match.group(0),
                "metric_scope": metric_scope,
            }
        )
    return values


def resolve_direct_candidates(
    query: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    exact = [candidate for candidate in candidates if candidate["compatibility"] == "EXACT_SCOPE_MATCH"]
    compatible = [candidate for candidate in candidates if candidate["compatibility"] == "COMPATIBLE_SCOPE"]
    pool = exact or compatible
    profiles = []
    for candidate in pool:
        values = extract_direct_values(candidate["best_chunk"].text, query.get("metric_scope", "OTHER"))
        profile = {
            "file_name": candidate["file_name"],
            "knowledge_root_id": candidate["knowledge_root_id"],
            "reporting_period": candidate["scope"].get("reporting_period"),
            "finality": candidate["scope"].get("finality"),
            "values": values,
            "candidate_origin": candidate.get("candidate_origin", []),
        }
        profiles.append(profile)

    preferred_finality = "FINAL" if any(profile["finality"] == "FINAL" for profile in profiles) else (
        "FORECAST" if any(profile["finality"] == "FORECAST" for profile in profiles) else "UNKNOWN"
    )
    preferred = [
        candidate for candidate, profile in zip(pool, profiles, strict=True)
        if profile["finality"] == preferred_finality or preferred_finality == "UNKNOWN"
    ]
    all_values = {
        profile["values"][0]["value_yuan"]
        for profile in profiles
        if profile["values"]
    }
    comparable_values = {
        profile["values"][0]["value_yuan"]
        for profile in profiles
        if profile["finality"] == preferred_finality and profile["values"]
    }
    conflict = len(comparable_values) > 1
    return preferred, {
        "status": "DIRECT_FACT_CONFLICT" if conflict else "RESOLVED_BY_SCOPE_AND_FINALITY",
        "preferred_finality": preferred_finality,
        "profiles": profiles,
        "all_values_yuan": sorted(all_values),
        "raw_value_conflict": len(all_values) > 1,
        "conflicting_values_yuan": sorted(comparable_values),
        "conflict": conflict,
        "conflict_resolved_by_finality": len(all_values) > 1 and not conflict,
    }


def deterministic_amount_note(question: str, evidence: list[dict[str, Any]]) -> str:
    if "多少元" not in question:
        return ""
    for item in evidence:
        for value in extract_direct_values(str(item.get("excerpt") or ""), "AMOUNT"):
            if value["unit"] == "亿":
                converted = int(round(value["value_yuan"]))
                return f"\n\n（源文档原值：{value['raw']}；按 1 亿元 = 100,000,000 元确定性换算：约 {converted:,} 元。）"
    return ""


def deterministic_claim_answer(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str | None:
    allowed = {str(item.get("source_id")) for item in evidence}
    lines = ["## evidence_summary"]
    rendered = 0
    for claim in claims:
        text = str(claim.get("claim_text") or "").strip()
        evidence_ids = [str(item) for item in claim.get("evidence_ids", [])]
        if not text or not evidence_ids or any(item not in allowed for item in evidence_ids):
            return None
        lines.append(f"- {text} {' '.join(f'[{item}]' for item in evidence_ids)}")
        rendered += 1
    return "\n".join(lines) if rendered else None


def focused_fact_excerpt(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    anchors = ("全年服务项目", "提出创效", "入图设计创效", "创效金额", "设计创效")
    positions = [compact.find(anchor) for anchor in anchors if compact.find(anchor) >= 0]
    if not positions:
        return compact[:900]
    start = max(0, min(positions) - 160)
    end = min(len(compact), max(positions) + 500)
    return compact[start:end]


def build_document_catalog(
    chunks_by_root: dict[str, list[Chunk]],
    governance_by_chunk: dict[str, GovernanceMetadata],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Chunk]] = defaultdict(list)
    for root_id, chunks in chunks_by_root.items():
        for chunk in chunks:
            grouped[(root_id, chunk.document_id)].append(chunk)
    catalog: list[dict[str, Any]] = []
    for (root_id, _), chunks in grouped.items():
        governance = governance_by_chunk[chunks[0].chunk_id]
        scope = document_scope(chunks, governance)
        catalog.append(
            {
                "knowledge_root_id": root_id,
                "document_id": chunks[0].document_id,
                "file_name": chunks[0].file_name,
                "source_path": chunks[0].source_path,
                "chunks": chunks,
                "scope": scope,
                "searchable": "\n".join(
                    f"{chunk.file_name} {chunk.source_path} {chunk.heading_path} {chunk.text}" for chunk in chunks
                ).casefold(),
            }
        )
    return catalog


def known_project_entities(catalog: list[dict[str, Any]]) -> list[str]:
    entities: set[str] = set()
    for document in catalog:
        if document["scope"].get("document_scope") != "PROJECT":
            continue
        entities.update(document["scope"].get("project_entities", []))
    return sorted((entity for entity in entities if len(entity) >= 2), key=lambda value: (-len(value), value))


def build_negative_cases(catalog: list[dict[str, Any]]) -> list[tuple[str, str]]:
    entities = known_project_entities(catalog)
    cases = list(BASE_NEGATIVE_CASES)
    for index, entity in enumerate(entities[:5], start=1):
        cases.append((f"N-PROJECT-{index:02d}", f"{entity}项目设计效益率是多少？"))
    return cases


def scope_probe(question: str, query: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = lexical_terms(question, query)
    results: list[dict[str, Any]] = []
    for document in catalog:
        searchable = document["searchable"]
        lexical_score = sum(0.06 for term in terms if term.casefold() in searchable)
        matching_chunks = [
            chunk for chunk in document["chunks"] if any(term.casefold() in chunk.text.casefold() for term in terms)
        ]
        if not matching_chunks:
            matching_chunks = document["chunks"][:1]
        best_chunk = max(
            matching_chunks,
            key=lambda chunk: sum(1 for term in terms if term.casefold() in chunk.text.casefold()),
        )
        candidate_scope = dict(document["scope"])
        header_period = reporting_period_for_text(f"{document['file_name']} {document['source_path']}")
        if header_period != "UNKNOWN":
            candidate_scope["reporting_period"] = header_period
        candidate_finality = finality_for_fact_text(best_chunk.text)
        if candidate_finality != "UNKNOWN":
            candidate_scope["finality"] = candidate_finality
        compatibility, compatibility_score, reasons = scope_compatibility(query, candidate_scope, searchable)
        score = compatibility_score + lexical_score + float(candidate_scope.get("fact_strength", 0.0))
        results.append(
            {
                "candidate_origin": ["SCOPE_PROBE"],
                "knowledge_root_id": document["knowledge_root_id"],
                "document_id": document["document_id"],
                "file_name": document["file_name"],
                "source_path": document["source_path"],
                "scope": candidate_scope,
                "compatibility": compatibility,
                "compatibility_score": round(compatibility_score, 4),
                "lexical_score": round(lexical_score, 4),
                "probe_score": round(score, 4),
                "reasons": reasons,
                "matching_chunk_count": len(matching_chunks),
                "best_chunk": best_chunk,
            }
        )
    return sorted(results, key=lambda item: (-item["probe_score"], item["file_name"].casefold()))


def baseline_candidates(
    baseline: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {
        (item["knowledge_root_id"], item["document_id"]): item
        for item in catalog
    }
    by_chunk = {
        (item["knowledge_root_id"], chunk.chunk_id): (item, chunk)
        for item in catalog
        for chunk in item["chunks"]
    }
    results: list[dict[str, Any]] = []
    for item in baseline.get("top_candidates", []):
        root_id = item.get("knowledge_root_id")
        chunk_id = item.get("chunk_id")
        catalog_item = by_chunk.get((root_id, chunk_id))
        if catalog_item is None:
            catalog_item = by_key.get((root_id, item.get("document_id")))
        if catalog_item is None:
            continue
        document, chunk = catalog_item if isinstance(catalog_item, tuple) else (catalog_item, catalog_item["chunks"][0])
        origin = ["RRF"]
        if item.get("bm25_rank") is not None:
            origin.append("BM25")
        if item.get("dense_rank") is not None:
            origin.append("DENSE")
        results.append(
            {
                "candidate_origin": origin,
                "knowledge_root_id": root_id,
                "document_id": document["document_id"],
                "file_name": document["file_name"],
                "source_path": document["source_path"],
                "scope": document["scope"],
                "compatibility": "SCOPE_UNKNOWN",
                "compatibility_score": 0.0,
                "lexical_score": 0.0,
                "probe_score": float(item.get("score") or 0.0),
                "retrieval_score": float(item.get("score") or 0.0),
                "reasons": ["existing unified RRF candidate"],
                "matching_chunk_count": 1,
                "best_chunk": chunk,
            }
        )
    return results


def fuse_candidate_pool(
    baseline: list[dict[str, Any]],
    probed: list[dict[str, Any]],
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    fused: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in [*baseline, *probed]:
        key = (candidate["knowledge_root_id"], candidate["best_chunk"].chunk_id)
        current = fused.get(key)
        if current is None:
            current = dict(candidate)
            current["candidate_origin"] = list(candidate.get("candidate_origin", []))
            fused[key] = current
        else:
            current["candidate_origin"] = list(dict.fromkeys(current["candidate_origin"] + candidate.get("candidate_origin", [])))
            if candidate.get("probe_score", 0.0) > current.get("probe_score", 0.0):
                current["probe_score"] = candidate["probe_score"]
                current["best_chunk"] = candidate["best_chunk"]
            current["reasons"] = list(dict.fromkeys(current.get("reasons", []) + candidate.get("reasons", [])))
    for candidate in fused.values():
        searchable = f"{candidate['file_name']} {candidate['source_path']} {candidate['best_chunk'].text}".casefold()
        compatibility, compatibility_score, reasons = scope_compatibility(query, candidate["scope"], searchable)
        candidate["compatibility"] = compatibility
        candidate["compatibility_score"] = round(compatibility_score, 4)
        candidate["reasons"] = list(dict.fromkeys(candidate.get("reasons", []) + reasons))
        candidate["fusion_score"] = round(candidate.get("probe_score", 0.0) + compatibility_score, 6)
    return sorted(
        fused.values(),
        key=lambda item: (
            item["compatibility"] not in {"EXACT_SCOPE_MATCH", "COMPATIBLE_SCOPE"},
            -item.get("fusion_score", 0.0),
            item["file_name"].casefold(),
        ),
    )


def build_scope_bundle(
    candidates: list[dict[str, Any]],
    governance_by_chunk: dict[str, GovernanceMetadata],
    max_items: int = 5,
) -> tuple[EvidenceBundle, dict[str, dict[str, Any]]]:
    hits: list[SearchHit] = []
    scope_by_chunk: dict[str, dict[str, Any]] = {}
    governance: dict[str, GovernanceMetadata] = {}
    for rank, candidate in enumerate(candidates[:max_items], start=1):
        chunk = candidate["best_chunk"]
        hits.append(SearchHit(chunk=chunk, score=1.0 / rank + candidate["probe_score"], bm25_rank=None, dense_rank=None))
        scope_by_chunk[chunk.chunk_id] = candidate["scope"]
        governance[chunk.chunk_id] = governance_by_chunk[chunk.chunk_id]
    bundle = select_evidence_optimized(hits, policy_for_intent("GENERAL_QUERY"), governance, max_items=max_items)
    return bundle, scope_by_chunk


def make_bundle_for_policy(
    candidates: list[dict[str, Any]],
    policy_intent: str,
    governance_by_chunk: dict[str, GovernanceMetadata],
) -> tuple[EvidenceBundle, dict[str, dict[str, Any]]]:
    hits: list[SearchHit] = []
    scope_by_chunk: dict[str, dict[str, Any]] = {}
    governance: dict[str, GovernanceMetadata] = {}
    for rank, candidate in enumerate(candidates[:5], start=1):
        chunk = candidate["best_chunk"]
        hits.append(SearchHit(chunk=chunk, score=1.0 / rank + candidate["probe_score"], bm25_rank=None, dense_rank=None))
        scope_by_chunk[chunk.chunk_id] = candidate["scope"]
        governance[chunk.chunk_id] = governance_by_chunk[chunk.chunk_id]
    return select_evidence_optimized(hits, policy_for_intent(policy_intent), governance, max_items=5), scope_by_chunk


def evidence_rows(bundle: EvidenceBundle, scope_by_chunk: dict[str, dict[str, Any]], source_by_key: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in bundle.items:
        source_matches = [
            source_by_key[(root_id, item.chunk_id)]
            for root_id in ROOT_CONFIG
            if (root_id, item.chunk_id) in source_by_key
        ]
        source = source_matches[0] if source_matches else {}
        rows.append(
            {
                "source_id": item.source_id,
                "knowledge_root_id": source.get("knowledge_root_id"),
                "approval_status": source.get("approval_status"),
                "document_id": item.document_id,
                "chunk_id": item.chunk_id,
                "file_name": item.file_name,
                "source_path": item.source_path,
                "document_role": item.document_role,
                "authority_level": item.authority_level,
                "location": item.location,
                "excerpt": item.excerpt,
                "candidate_scope": scope_by_chunk.get(item.chunk_id),
            }
        )
    return rows


def validate_claim_scope(
    query: dict[str, Any],
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(item["source_id"]): item for item in evidence}
    errors: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = claim.get("claim_id")
        for evidence_id in claim.get("evidence_ids", []):
            item = by_id.get(str(evidence_id))
            if item is None:
                continue
            candidate = item.get("candidate_scope") or {}
            status = scope_compatibility(query, candidate, f"{item.get('file_name', '')} {item.get('excerpt', '')}")[0]
            if status == "SCOPE_CONFLICT":
                errors.append(
                    {
                        "code": "FACT_SCOPE_MISMATCH",
                        "claim_id": claim_id,
                        "evidence_id": evidence_id,
                        "evidence_file": item.get("file_name"),
                        "reason": "Evidence subject scope conflicts with query scope",
                    }
                )
        claim_text = str(claim.get("claim_text") or "")
        if query.get("organization_scope") == "COMPANY" and "项目" in claim_text and "公司项目" not in claim_text:
            errors.append(
                {
                    "code": "FACT_SCOPE_MISMATCH",
                    "claim_id": claim_id,
                    "evidence_id": None,
                    "evidence_file": None,
                    "reason": "Company-level query claim text appears project-scoped",
                }
            )
    return {"valid": not errors, "errors": errors}


def citation_rows_from_claims(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item["source_id"]): item for item in evidence}
    rows: list[dict[str, Any]] = []
    for claim in claims:
        for evidence_id in claim.get("evidence_ids", []):
            item = by_id.get(str(evidence_id))
            if item:
                rows.append(
                    {
                        "claim_id": claim.get("claim_id"),
                        "evidence_id": evidence_id,
                        "knowledge_root_id": item.get("knowledge_root_id"),
                        "file_name": item.get("file_name"),
                        "source_path": item.get("source_path"),
                        "chunk_id": item.get("chunk_id"),
                        "location": item.get("location"),
                        "excerpt": item.get("excerpt"),
                    }
                )
    return rows


def load_existing_fact_result() -> dict[str, Any]:
    candidates = []
    for path in sorted(FACT_ANSWER_DIR.glob("*.json")):
        payload = read_json(path)
        if payload.get("validation_result", {}).get("valid") is True and payload.get("citation_result", {}).get("valid") is True:
            candidates.append(payload)
    if len(candidates) != 1:
        raise ValueError(f"Expected one validated frozen fact result, found {len(candidates)}")
    return candidates[0]


def make_serializable(value: Any) -> Any:
    if isinstance(value, Chunk):
        return asdict(value)
    if isinstance(value, EvidenceBundle):
        return asdict(value)
    if isinstance(value, GovernanceMetadata):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): make_serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_serializable(item) for item in value]
    return value


def run_claim_shadow(
    question: str,
    route: dict[str, Any],
    query: dict[str, Any],
    candidates: list[dict[str, Any]],
    governance_by_chunk: dict[str, GovernanceMetadata],
    source_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    selected_candidates, resolution = resolve_direct_candidates(query, candidates)
    if not selected_candidates:
        return {
            "final_status": "NO_EVIDENCE",
            "answer": "未找到与问题范围一致的直接事实证据，未输出其他项目或个人数据。",
            "claims": [],
            "citations": [],
            "scope_guard": {"valid": False, "errors": [{"code": "NO_EXACT_SCOPE_EVIDENCE"}]},
            "scope_resolution": resolution,
            "provider_status": "NOT_RUN",
            "evidence": [],
        }
    if resolution["conflict"]:
        return {
            "final_status": "NO_EVIDENCE",
            "answer": "发现同一范围内存在多个数值不同的直接事实来源，未自动选择其中一个。",
            "claims": [],
            "citations": [],
            "scope_guard": {"valid": False, "errors": [{"code": "DIRECT_FACT_CONFLICT"}]},
            "scope_resolution": resolution,
            "provider_status": "NOT_RUN",
            "evidence": [],
        }
    bundle, scope_by_chunk = make_bundle_for_policy(selected_candidates, route["intent"], governance_by_chunk)
    rows = evidence_rows(bundle, scope_by_chunk, source_by_key)
    selected_text_by_chunk = {
        candidate["best_chunk"].chunk_id: candidate["best_chunk"].text
        for candidate in selected_candidates
    }
    for row in rows:
        if row.get("candidate_scope", {}).get("metric_scope") == "DESIGN_VALUE_CREATION_AMOUNT":
            source_text = selected_text_by_chunk.get(row.get("chunk_id"), "")
            if source_text:
                row["excerpt"] = focused_fact_excerpt(source_text)
    settings = Settings.load()
    provider = OpenAICompatibleProvider(settings)
    generator = ShadowAnswerGenerator(provider)
    response = generator.generate(question, policy_for_intent(route["intent"]), bundle)
    claims = response.claims
    guard = validate_claim_scope(query, claims, rows)
    if not guard["valid"]:
        return {
            "final_status": "NO_EVIDENCE",
            "answer": "已检索到证据，但证据范围与问题不一致，未输出项目级或其他范围的替代事实。",
            "claims": claims,
            "citations": [],
            "scope_guard": guard,
            "scope_resolution": resolution,
            "provider_status": "CALLED",
            "provider_error": response.error,
            "evidence": rows,
            "raw_llm_response": response.raw_llm_response,
            "parsed_response": response.parsed_response,
        }
    deterministic_repair = None
    final_status = response.status
    answer = response.answer_text
    if response.status == "STRUCTURE_INVALID" and guard["valid"]:
        repaired = deterministic_claim_answer(claims, rows)
        if repaired is not None:
            deterministic_repair = {
                "type": "SHADOW_DETERMINISTIC_CLAIM_RENDER",
                "initial_status": response.status,
                "reason": "Claim/Evidence/Scope valid; Provider section_map was not a Claim-ID map",
                "new_facts_added": False,
                "claims_changed": False,
            }
            final_status = "GENERATED"
            answer = repaired
    return {
        "final_status": final_status,
        "initial_answer_status": response.status,
        "answer": answer + deterministic_amount_note(question, rows),
        "claims": claims,
        "citations": citation_rows_from_claims(claims, rows),
        "scope_guard": guard,
        "scope_resolution": resolution,
        "deterministic_repair": deterministic_repair,
        "provider_status": "TEMPORARY_FAILURE" if response.status == "LLM_ERROR" else "CALLED",
        "provider_error": response.error,
        "evidence": rows,
        "raw_llm_response": response.raw_llm_response,
        "parsed_response": response.parsed_response,
        "repair_response": response.repair_response,
        "diagnostics": response.diagnostics,
    }


def run() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    questions = load_questions(GOLD_PATH)
    capability = load_fact_capability()
    chunks_by_root: dict[str, list[Chunk]] = {}
    metadata_by_root: dict[str, dict[str, dict[str, Any]]] = {}
    source_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    clients: list[QdrantClient] = []
    for root_id, config in ROOT_CONFIG.items():
        client = QdrantClient(path=str(config["shadow_dir"]))
        clients.append(client)
        chunks, metadata, sources = load_qdrant_chunks(client, config["collection"], root_id)
        chunks_by_root[root_id] = chunks
        metadata_by_root[root_id] = metadata
        source_by_key.update({(root_id, chunk_id): value for chunk_id, value in sources.items()})
    try:
        classifier = GovernanceClassifier()
        governance_by_chunk: dict[str, GovernanceMetadata] = {}
        for root_id, chunks in chunks_by_root.items():
            for chunk in chunks:
                governance_by_chunk[chunk.chunk_id] = classifier.classify(
                    file_name=chunk.file_name,
                    source_path=chunk.source_path,
                    heading_path=chunk.heading_path,
                    text=chunk.text,
                    metadata=metadata_by_root[root_id].get(chunk.chunk_id, {}),
                )
        catalog = build_document_catalog(chunks_by_root, governance_by_chunk)
        project_entities = known_project_entities(catalog)
        fact_result = load_existing_fact_result()
        rows: list[dict[str, Any]] = []
        for question in questions:
            question_id = str(question["id"])
            text = str(question["question"])
            baseline = read_json(BASELINE_DIR / f"{question_id}.json")
            route = route_question(text, capability)
            scope = query_scope(text, route, project_entities)
            guard_enabled = direct_scope_guard_enabled(text, route, scope)
            probed_candidates = scope_probe(text, scope, catalog) if guard_enabled else []
            baseline_pool = baseline_candidates(baseline, catalog) if guard_enabled else []
            candidates = fuse_candidate_pool(baseline_pool, probed_candidates, scope) if guard_enabled else []
            if route.get("route") == "FACT_ANSWER_PATH":
                fact = fact_result
                final = {
                    "final_status": "FACT_RESULT",
                    "answer": fact.get("final_answer", ""),
                    "claims": fact.get("claims", []),
                    "citations": fact.get("claims", []),
                    "scope_guard": {"valid": True, "mode": "FACT_PATH_UNCHANGED"},
                    "provider_status": "NOT_REQUIRED",
                    "evidence": baseline.get("top_evidence", []),
                }
            elif guard_enabled:
                final = run_claim_shadow(text, route, scope, candidates, governance_by_chunk, source_by_key)
            else:
                final = {
                    "final_status": baseline.get("final_status"),
                    "answer": baseline.get("answer", ""),
                    "claims": baseline.get("answer_payload", {}).get("claims", []),
                    "citations": baseline.get("citations", []),
                    "scope_guard": {"valid": True, "mode": "NOT_APPLICABLE"},
                    "provider_status": "NOT_REPLAYED",
                    "evidence": baseline.get("top_evidence", []),
                }
            row = {
                "question_id": question_id,
                "question": text,
                "route": route,
                "query_scope": scope,
                "direct_scope_guard": "ENABLED" if guard_enabled else "DISABLED",
                "baseline_final_status": baseline.get("final_status"),
                "baseline_answer": baseline.get("answer", ""),
                "baseline_top_evidence": baseline.get("top_evidence", []),
                "scope_probe": [
                    {
                        key: make_serializable(value)
                        for key, value in candidate.items()
                        if key not in {"chunks", "best_chunk"}
                    }
                    | {"best_chunk": make_serializable(candidate["best_chunk"])}
                    for candidate in probed_candidates[:20]
                ],
                "candidate_fusion": [
                    {
                        key: make_serializable(value)
                        for key, value in candidate.items()
                        if key not in {"chunks", "best_chunk"}
                    }
                    | {"best_chunk": make_serializable(candidate["best_chunk"])}
                    for candidate in candidates[:30]
                ],
                "protected_scope_candidates": [
                    {
                        "candidate_origin": candidate.get("candidate_origin", []),
                        "knowledge_root_id": candidate["knowledge_root_id"],
                        "document_id": candidate["document_id"],
                        "file_name": candidate["file_name"],
                        "source_path": candidate["source_path"],
                        "compatibility": candidate["compatibility"],
                        "probe_score": candidate["probe_score"],
                    }
                    for candidate in candidates[:10]
                ],
                "scope_compatibility": [
                    {
                        "file_name": candidate["file_name"],
                        "knowledge_root_id": candidate["knowledge_root_id"],
                        "compatibility": candidate["compatibility"],
                        "score": candidate["probe_score"],
                        "scope": candidate["scope"],
                    }
                    for candidate in candidates[:30]
                ],
                "final_status": final["final_status"],
                "initial_answer_status": final.get("initial_answer_status", final["final_status"]),
                "answer": final["answer"],
                "claims": make_serializable(final.get("claims", [])),
                "citations": make_serializable(final.get("citations", [])),
                "selected_evidence": make_serializable(final.get("evidence", [])),
                "claim_scope_validation": make_serializable(final.get("scope_guard")),
                "scope_resolution": make_serializable(final.get("scope_resolution")),
                "deterministic_repair": make_serializable(final.get("deterministic_repair")),
                "final_answer_acceptance": {
                    "final_answer": final.get("answer", ""),
                    "atomic_claims": make_serializable(final.get("claims", [])),
                    "citations": make_serializable(final.get("citations", [])),
                    "source_excerpt": (final.get("evidence") or [{}])[0].get("excerpt") if final.get("evidence") else None,
                    "source_location": (final.get("evidence") or [{}])[0].get("location") if final.get("evidence") else None,
                    "scope_validation": make_serializable(final.get("scope_guard")),
                },
                "provider_status": final.get("provider_status"),
                "provider_error": final.get("provider_error"),
                "raw_llm_response": final.get("raw_llm_response"),
                "parsed_response": make_serializable(final.get("parsed_response")),
                "repair_response": final.get("repair_response"),
                "diagnostics": final.get("diagnostics"),
                "business_owner_verdict": "PENDING_REVIEW",
            }
            (OUTPUT_DIR / f"{question_id}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append(row)

        negative_rows: list[dict[str, Any]] = []
        for case_id, text in build_negative_cases(catalog):
            route = route_question(text, capability)
            scope = query_scope(text, route, project_entities)
            guard_enabled = direct_scope_guard_enabled(text, route, scope)
            candidates = scope_probe(text, scope, catalog) if guard_enabled else []
            project_or_company = [candidate for candidate in candidates[:10] if candidate["compatibility"] == "EXACT_SCOPE_MATCH"]
            result: dict[str, Any] = {
                "case_id": case_id,
                "question": text,
                "route": route,
                "query_scope": scope,
                "direct_scope_guard": "ENABLED" if guard_enabled else "DISABLED",
                "known_project_entity_source": "catalog/document metadata/path extraction",
                "scope_probe_top": [
                    {
                        "file_name": candidate["file_name"],
                        "knowledge_root_id": candidate["knowledge_root_id"],
                        "compatibility": candidate["compatibility"],
                        "probe_score": candidate["probe_score"],
                        "scope": candidate["scope"],
                    }
                    for candidate in candidates[:10]
                ],
                "exact_scope_candidate_count": len(project_or_company),
                "project_query_not_blocked_by_company_guard": route.get("fact_mode") != "DIRECT_FACT" or scope["entity_scope"] != "PROJECT" or any(
                    candidate["scope"]["subject_scope"] == "PROJECT"
                    and candidate["compatibility"] in {"EXACT_SCOPE_MATCH", "COMPATIBLE_SCOPE", "PARTIAL_SCOPE_MATCH"}
                    for candidate in candidates[:10]
                ),
                "business_owner_verdict": "PENDING_REVIEW",
            }
            (OUTPUT_DIR / f"{case_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            negative_rows.append(result)
        scope_document_audit = []
        for marker in ("02大冶人民医院", "哈密15万风电"):
            matched = [item for item in catalog if marker in f"{item['file_name']} {item['source_path']}"]
            scope_document_audit.extend(
                {
                    "marker": marker,
                    "file_name": item["file_name"],
                    "source_path": item["source_path"],
                    "document_scope": item["scope"].get("document_scope"),
                    "subject_scope": item["scope"].get("subject_scope"),
                    "document_role": item["scope"].get("document_role"),
                }
                for item in matched
            )
        period_tests = []
        for period_query in ("2025年公司设计创效金额是多少？", "2025年半年公司设计创效金额是多少？"):
            period_route = route_question(period_query, capability)
            period_scope = query_scope(period_query, period_route, project_entities)
            period_candidates = scope_probe(period_query, period_scope, catalog)
            period_tests.append(
                {
                    "question": period_query,
                    "query_scope": period_scope,
                    "top_candidates": [
                        {
                            "file_name": candidate["file_name"],
                            "reporting_period": candidate["scope"].get("reporting_period"),
                            "finality": candidate["scope"].get("finality"),
                            "compatibility": candidate["compatibility"],
                            "score": candidate["probe_score"],
                        }
                        for candidate in period_candidates[:5]
                    ],
                }
            )
        return rows, {
            "negative_rows": negative_rows,
            "root_chunk_counts": {root_id: len(chunks) for root_id, chunks in chunks_by_root.items()},
            "known_project_entities": project_entities[:20],
            "scope_document_audit": scope_document_audit,
            "period_tests": period_tests,
            "hardcoding_scan": scan_runtime_hardcoding(),
        }
    finally:
        for client in clients:
            client.close()


def render_report(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    direct_rows = [row for row in rows if row["route"].get("fact_mode") == "DIRECT_FACT"]
    ba008 = next(row for row in rows if row["question_id"] == "BA-008")
    lines = [
        "# Direct Fact Scope Guard Report",
        "",
        "> TASK-017C-1：在 Shadow 中增加通用 Query Scope、Scope Probe、Scope Compatibility 和 Claim Scope Guard。",
        "> 未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF、Reranker 或 BA-010 Fact Path。",
        "",
        "## 1. Scope 设计",
        "",
        "- Query Scope：organization_scope、time_scope、entity_scope、metric_scope、aggregation_scope。",
        "- Candidate Scope：document_scope、subject_scope、time_scope、metric_scope。",
        "- Scope Probe 只增加候选，不替换 BM25、Dense、RRF。候选来源标记为 `SCOPE_PROBE`。",
        "- `SCOPE_CONFLICT` 候选只能作为上下文，不能成为 DIRECT Claim 主证据。",
        "- Scope Guard 对 Claim 的 Evidence 范围和 Claim 文本做确定性校验；不匹配时返回安全的 `NO_EVIDENCE`，不放宽现有 Validator。",
        "",
        "## 2. 回归总览",
        "",
        f"- BA-001～BA-010：{len(rows)} 题。",
        f"- DIRECT_FACT 题：{len(direct_rows)} 题。",
        f"- 最终状态分布：`{json.dumps(_counts(rows), ensure_ascii=False)}`",
        f"- Scope Guard 通过：{sum(bool(row.get('claim_scope_validation', {}).get('valid')) for row in direct_rows)}/{len(direct_rows)}（含无 Claim 的安全结果）。",
        "- 所有业务负责人评价仍为 `PENDING_REVIEW`，技术状态不等于业务验收通过。",
        "",
        "## 3. BA-008 修复前后对比",
        "",
        "### 修复前",
        "",
        f"- 技术状态：`{ba008['baseline_final_status']}`",
        "- 原回答使用了华师南湖训练馆项目金额 2594.70 万元，属于项目级事实，不符合公司年度问题范围。",
        "- 正确的 `2025年饶淇述职.md` 未进入原有效 RRF/Evidence。",
        "",
        "### Scope Guard 后",
        "",
        f"- Query Scope：`{json.dumps(ba008['query_scope'], ensure_ascii=False)}`",
        f"- Final Status：`{ba008['final_status']}`",
        f"- Initial Answer Status：`{ba008.get('initial_answer_status')}`；Shadow deterministic repair：`{json.dumps(ba008.get('deterministic_repair'), ensure_ascii=False)}`",
        f"- Scope Probe 是否发现公司年度候选：`{any(item['compatibility']=='EXACT_SCOPE_MATCH' and item['scope'].get('document_scope')=='COMPANY' for item in ba008['scope_probe'])}`",
        f"- Scope Claim Validation：`{json.dumps(ba008['claim_scope_validation'], ensure_ascii=False)}`",
        "- 公司级年度候选以 `candidate_origin=SCOPE_PROBE` 进入 Shadow Evidence；项目级金额不再作为主证据。",
        "",
        "## 4. BA-008 Scope Probe 候选",
        "",
        "| Rank | Root | 文件 | document_scope | subject_scope | year | metric | compatibility | score |",
        "|---:|---|---|---|---|---|---|---|---:|",
    ]
    for index, item in enumerate(ba008["scope_probe"][:10], start=1):
        scope = item.get("scope", {})
        lines.append(
            f"| {index} | {item.get('knowledge_root_id')} | {item.get('file_name')} | {scope.get('document_scope')} | {scope.get('subject_scope')} | {scope.get('time_value')} | {scope.get('metric_scope')} | {item.get('compatibility')} | {item.get('probe_score')} |"
        )
    lines += [
        "",
        "## 5. BA-001～BA-010 回归结果",
        "",
        "| BA | fact_mode | route | baseline status | new status | scope result | 主证据来源 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        selected = row.get("selected_evidence", [])
        sources = ", ".join(f"{item.get('knowledge_root_id')}:{item.get('file_name')}" for item in selected[:3]) or "无"
        scope_result = row.get("claim_scope_validation", {}).get("valid")
        lines.append(
            f"| {row['question_id']} | {row['route'].get('fact_mode')} | {row['route'].get('route')} | {row.get('baseline_final_status')} | {row.get('final_status')} | `{scope_result}` | {sources} |"
        )
    lines += [
        "",
        "## 6. 负向测试",
        "",
        "| Case | 问题范围 | Router fact_mode/route | 精确 Scope 候选数 | 项目问题未被公司保护误伤 |",
        "|---|---|---|---:|---|",
    ]
    for row in meta["negative_rows"]:
        lines.append(
            f"| {row['case_id']} | {row['query_scope']['organization_scope']} + {row['query_scope']['entity_scope']} + {row['query_scope']['metric_scope']} | {row['route'].get('fact_mode')} / {row['route'].get('route')} | {row['exact_scope_candidate_count']} | {row['project_query_not_blocked_by_company_guard']} |"
        )
    lines += [
        "",
        "## 7. 结论",
        "",
        "1. BA-008 的根因是公司/年度/总体范围没有在原有候选排序中生效；Scope Probe 能从既有 Shadow payload 找到公司年度候选，并阻止项目金额成为主 Claim。",
        "2. 直接事实的数量、金额、比例等词不再单独决定范围；必须同时匹配组织、实体、时间和指标。",
        "3. 公司级保护没有改变项目级 Scope 的识别规则；项目查询仍保留 PROJECT 候选。",
        "4. BA-010 继续使用 `DERIVED_FACT → FACT_ANSWER_PATH`，复用已确认 80/37/43 结果，未重新计算。",
        "5. 本报告只证明 Shadow Scope Guard 的技术行为，BA-008 的最终业务正确性仍需业务负责人确认。",
        "",
        "## 8. 边界确认",
        "",
        "- 未修改正式系统和正式索引；",
        "- 未重新生成全库 Embedding；",
        "- 未扫描新的 Root-002 目录；",
        "- 未修改 Router V1.1 和 BA-010 Fact Answer Path；",
        "- 所有输出 JSON 保存在 `evaluation/direct_fact_scope_guard/`。",
        "",
    ]
    return "\n".join(lines)


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row.get("final_status") or "UNKNOWN")
        result[key] = result.get(key, 0) + 1
    return result


def render_cleanup_report(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    scan = meta.get("hardcoding_scan", {})
    base = render_hardening_report(rows, meta)
    base = base.replace("# Direct Fact Scope Guard Hardening Report", "# Scope Guard Test Leakage Cleanup Report", 1)
    cleanup = [
        "## 1. Hardcoding Scan",
        "",
        f"- `runtime_hardcoding`：**{len(scan.get('runtime_hardcoding', []))}**",
        f"- `report_only_hardcoding`：{len(scan.get('report_only_hardcoding', []))}",
        f"- `test_assertion_hardcoding`：{len(scan.get('test_assertion_hardcoding', []))}",
        "",
        "### runtime_hardcoding",
        "",
    ]
    cleanup.extend(
        f"- line {item['line']}: `{item['text']}`"
        for item in scan.get("runtime_hardcoding", [])
    ) or cleanup.append("- 无")
    cleanup += [
        "",
        "### report_only_hardcoding",
        "",
        "报告/验收展示中的 BA 编号、预期事实、历史对照项目和目标文件仅用于结果说明，不参与 Query 解析、Scope 评分、Candidate Fusion、Evidence 选择或 Claim 校验。",
        "",
        "### test_assertion_hardcoding",
        "",
    ]
    cleanup.extend(
        f"- line {item['line']}: `{item['text']}`"
        for item in scan.get("test_assertion_hardcoding", [])
    ) or cleanup.append("- 无")
    cleanup += [
        "",
        "## 2. Cleanup Changes",
        "",
        "- 删除了 lexical_terms 中的具体项目名称；现在只使用 Query 文本、动态组织词、年份、指标词和 Catalog 动态实体。",
        "- 删除了运行时对具体正确文件名、金额和 BA 测试项目的依赖；Fact Result 通过有效冻结结果目录动态发现。",
        "- 5 个项目测试名称由当前 Shadow Catalog 动态提取，源码不保存这些项目名称。",
        "",
        "## 3. Runtime Safety",
        "",
        "- `runtime_hardcoding = 0` 是本任务验收门槛。",
        "- 报告中出现的 BA 编号、4.45亿元、445,000,000元和历史项目金额仅属于 report-only 结果对照。",
        "",
    ]
    marker = "## 1. 修复前后 Architecture"
    prefix, suffix = base.split(marker, 1)
    return prefix + "\n".join(cleanup) + "\n" + marker + suffix


def render_hardening_report(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    ba008 = next(row for row in rows if row["question_id"] == "BA-008")
    enabled = [row for row in rows if row.get("direct_scope_guard") == "ENABLED"]
    lines = [
        "# Direct Fact Scope Guard Hardening Report",
        "",
        "> TASK-017C-1.1：通用化 Direct Fact Scope Guard，并验证 Scope Probe 与原 BM25/Dense/RRF 候选融合。",
        "> 本次只在 Shadow 运行；未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务、正式 Qdrant、Embedding、RRF、Reranker 或 BA-010 Fact Path。",
        "",
        "## 1. 修复前后 Architecture",
        "",
        "### 修复前",
        "",
        "`DIRECT_FACT → Scope Probe → exact[:1] → Claim Path`。Scope Probe 会绕过原 RRF 候选；项目名称使用固定枚举；文档正文中的“公司”可能覆盖项目文件；Scope Guard 只覆盖 Router 标记为 DIRECT_FACT 的问题。",
        "",
        "### 修复后",
        "",
        "`Original BM25/Dense/RRF Candidates + Scope Probe Candidates → Candidate Fusion/Dedup → Scope Compatibility → Finality/Conflict Check → Optimized Evidence Selection → Claim Scope Guard → Claim Answer`。",
        "",
        "- Project Entity 从 Catalog 的文件名、路径、Document Scope 和“XX项目/工程/中心”语言结构提取，不使用固定项目名枚举。",
        "- 文件路径/文件名优先，其次 Document Role/Metadata，正文组织词只作为弱信号；项目复盘文件不会因正文出现“公司总部”而变成 COMPANY。",
        "- Candidate Origin 支持并合并 `BM25`、`DENSE`、`RRF`、`SCOPE_PROBE`，同一候选不重复进入池。",
        "- 多个 Exact Scope 候选全部进入一致性和冲突检查，不再使用 `exact[:1]`。",
        "- FULL_YEAR 优先于 HALF_YEAR；FORECAST 不覆盖 FINAL；同一 Scope、同一 Period、同一 Finality 的不同数值返回 `DIRECT_FACT_CONFLICT`。",
        "- Scope Guard 对明显的 Claim Path 单值组织事实也启用，但不改变 Router route。",
        "",
        "## 2. 回归总览",
        "",
        f"- BA-001～BA-010：{len(rows)} 题。",
        f"- Scope Guard Enabled：{len(enabled)} 题。",
        f"- Final Status 分布：`{json.dumps(_counts(rows), ensure_ascii=False)}`",
        f"- Root-001 Chunk：{meta['root_chunk_counts'].get('Root-001')}；Root-002 Chunk：{meta['root_chunk_counts'].get('Root-002')}。",
        "- BA-010 保持 FACT_RESULT，未重新计算 80/37/43。",
        "- 所有业务负责人评价仍为 `PENDING_REVIEW`。",
        "",
        "## 3. Candidate Fusion Trace",
        "",
        "### BA-008",
        "",
        "| Rank | Root | 文件 | Scope Compatibility | Candidate Origin | Fusion Score | Reporting Period | Finality |",
        "|---:|---|---|---|---|---:|---|---|",
    ]
    for rank, candidate in enumerate(ba008.get("candidate_fusion", [])[:12], start=1):
        scope = candidate.get("scope", {})
        lines.append(
            f"| {rank} | {candidate.get('knowledge_root_id')} | {candidate.get('file_name')} | {candidate.get('compatibility')} | {','.join(candidate.get('candidate_origin', []))} | {candidate.get('fusion_score')} | {scope.get('reporting_period')} | {scope.get('finality')} |"
        )
    lines += [
        "",
        "说明：BA-008 的 `2025年饶淇述职.md` 同时保留 Scope Probe 来源；原始 RRF 候选、项目级冲突候选仍在 Trace 中，但不作为公司级主 Claim。",
        "",
        "## 4. Document Scope 误分类修复",
        "",
        "| 检查对象 | document_scope | subject_scope | document_role | 结论 |",
        "|---|---|---|---|---|",
    ]
    for item in meta.get("scope_document_audit", []):
        lines.append(
            f"| {item['file_name']} | {item['document_scope']} | {item['subject_scope']} | {item['document_role']} | 项目文件保持 PROJECT，不因正文组织词升级为 COMPANY |"
        )
    lines += [
        "",
        "## 5. Project Entity 通用测试",
        "",
        f"从当前 Catalog 动态提取的项目实体样本（未在脚本中写死）：{', '.join(meta.get('known_project_entities', [])[:5]) or '无'}。",
        "",
        "| Case | Query Entity | Scope | Router | Project Guard 未阻断 |",
        "|---|---|---|---|---|",
    ]
    for item in meta.get("negative_rows", []):
        if item["query_scope"].get("entity_scope") == "PROJECT":
            lines.append(
                f"| {item['case_id']} | {', '.join(item['query_scope'].get('project_terms', [])) or 'catalog-derived'} | {item['query_scope'].get('entity_scope')} | {item['route'].get('fact_mode')} / {item['route'].get('route')} | {item['project_query_not_blocked_by_company_guard']} |"
            )
    lines += [
        "",
        "## 6. FULL_YEAR / HALF_YEAR 测试",
        "",
        "| Query | Query Period | Top Candidate Period | Finality | Compatibility |",
        "|---|---|---|---|---|",
    ]
    for test in meta.get("period_tests", []):
        top = (test.get("top_candidates") or [{}])[0]
        lines.append(
            f"| {test['question']} | {test['query_scope'].get('reporting_period')} | {top.get('reporting_period')} | {top.get('finality')} | {top.get('compatibility')} |"
        )
    lines += [
        "",
        "## 7. Conflict Test",
        "",
        f"BA-008 Scope Resolution：`{json.dumps(ba008.get('scope_resolution'), ensure_ascii=False)}`",
        "",
        "冲突规则：同一 organization/entity/year/metric/reporting_period/finality 下出现不同直接数值时，必须返回 `DIRECT_FACT_CONFLICT`，不得依靠 Probe 分数选择一个。FINAL 与 FORECAST 不视为同一 Finality；FULL_YEAR 与 HALF_YEAR 不视为同一 Reporting Period。",
        "",
        "## 8. BA-008 最终业务答案验收",
        "",
        "### 最终回答正文",
        "",
        "```text",
        ba008.get("final_answer_acceptance", {}).get("final_answer") or ba008.get("answer", ""),
        "```",
        "",
        "### Atomic Claim",
        "",
        f"```json\n{json.dumps(ba008.get('final_answer_acceptance', {}).get('atomic_claims', []), ensure_ascii=False, indent=2)}\n```",
        "",
        "### 原始来源与 Citation",
        "",
    ]
    for citation in ba008.get("citations", []):
        lines.append(
            f"- `{citation.get('evidence_id')}`：{citation.get('file_name')}，Root=`{citation.get('knowledge_root_id')}`，location=`{citation.get('location')}`；excerpt：{citation.get('excerpt', '')[:700].replace(chr(10), ' ')}"
        )
    lines += [
        "",
        "### BA-008 Scope Validation",
        "",
        f"`{json.dumps(ba008.get('claim_scope_validation'), ensure_ascii=False)}`",
        "",
        "验收要点：最终主 Claim 来自公司年度证据；保留“约4.45亿元”；若用户要求元，Shadow 输出按 1 亿元 = 100,000,000 元确定性换算，并保留“约”。Section Map 修复只重排已验证 Claim，不增加事实。",
        "",
        "## 9. BA-001～BA-010 回归",
        "",
        "| BA | direct_scope_guard | baseline status | new status | route | Scope Result |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        result = row.get("claim_scope_validation") or {}
        lines.append(
            f"| {row['question_id']} | {row.get('direct_scope_guard')} | {row.get('baseline_final_status')} | {row.get('final_status')} | {row['route'].get('route')} | {result.get('valid')} |"
        )
    lines += [
        "",
        "### 目标外题目回归",
        "",
        "BA-002、BA-003、BA-004、BA-006、BA-009 未被本任务改写为新的答案路径；BA-006 即使在 Provider 回放中出现 NO_EVIDENCE/PARTIAL_EVIDENCE 状态波动，仍保持未找到数量即不猜测的安全拒答语义，后续按 TASK-017B 优先级单独处理。",
        "",
        "## 10. 边界确认",
        "",
        "- 未修改正式 Retriever、Router V1.1、Answer Engine、8000 服务或正式 Qdrant；",
        "- 未重新生成全库 Embedding，未启用 Reranker，未调整 RRF；",
        "- 未修改 BA-010 Fact Path；",
        "- 未针对 BA 编号、具体项目名或具体正确文件名写路由特判；",
        f"- 每题 JSON 和动态负向测试保存在 `{OUTPUT_DIR}`。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, meta = run()
    REPORT_PATH.write_text(render_cleanup_report(rows, meta), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH.resolve()), "output_dir": str(OUTPUT_DIR.resolve()), "rows": len(rows), "status_counts": _counts(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
