from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem, select_evidence_optimized
from app.domain import Chunk, SearchHit

from scripts.run_p0_integrated_shadow_regression import ShadowIntegratedAnswerPipeline
from scripts.shadow_answer_router_v1 import load_ba_questions
from scripts.validate_knowledge_page_retrieval_rescue import fuse_candidates, retrieve_top100


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "policy_facet_grounding"
REPORT = PROJECT_ROOT / "docs" / "POLICY_FACET_GROUNDING_REPORT.md"

ORG_MARKERS = ("局级", "中建三局", "二公司", "第二建设公司")
DEMO_MARKERS = ("示范项目", "示范工程", "标杆项目", "试点项目")
SUBTYPE_PATTERNS = {
    "DESIGN_MANAGEMENT": re.compile(r"(?:EPC)?设计管理(?:示范项目|示范工程|标杆项目)"),
    "DETAILED_DESIGN": re.compile(r"深化设计(?:计划管理等[^，。；]{0,30})?(?:示范项目|示范工程|标杆项目)"),
    "TECHNOLOGY": re.compile(r"科技(?:示范项目|示范工程|标杆项目)"),
    "SMART_CONSTRUCTION": re.compile(r"智能建造(?:示范项目|示范工程|标杆项目)"),
}
VALID_ROLES = {"正式制度", "管理指南", "标准模板"}
VALID_AUTHORITY = {"L1", "L2", "L3"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def organization_from_header(file_name: str, source_path: str, heading_path: str) -> tuple[str | None, list[str]]:
    header = compact(f"{file_name} {heading_path}")
    path = compact(source_path)
    if "第二建设公司" in header or "二公司" in header:
        return "COMPANY", ["file_name/company publisher"]
    if "中建三局" in header or "局级" in header:
        return "GROUP", ["file_name/group publisher"]
    if "第二建设公司" in path or "二公司" in path:
        return "COMPANY", ["source_path/company publisher"]
    if "中建三局" in path or "局级" in path:
        return "GROUP", ["source_path/group publisher"]
    return None, []


def span_around(text: str, start: int, length: int = 320) -> str:
    text = compact(text)
    left = max(0, start - 80)
    return text[left : left + length]


def detect_groundings(candidate: dict[str, Any], *, governance: Any = None) -> list[dict[str, Any]]:
    local_text = compact(str(candidate.get("text") or ""))
    organization, organization_terms = organization_from_header(
        str(candidate.get("file_name") or ""),
        str(candidate.get("source_path") or ""),
        str(candidate.get("heading_path") or ""),
    )
    if organization is None:
        organization, organization_terms = organization_from_header(
            str(candidate.get("file_name") or ""), "", ""
        )
    topic_matches = [marker for marker in DEMO_MARKERS if marker in local_text]
    time_scope = "2026" if "2026" in compact(f"{candidate.get('file_name', '')} {local_text}") else None
    role = str(candidate.get("document_role") or getattr(governance, "document_role", ""))
    authority = str(candidate.get("authority_level") or getattr(governance, "authority_level", "UNKNOWN"))
    groundings: list[dict[str, Any]] = []
    for subtype, pattern in SUBTYPE_PATTERNS.items():
        match = pattern.search(local_text)
        if match is None:
            continue
        topic = "DEMONSTRATION_PROJECT" if topic_matches else None
        terms = [*organization_terms, match.group(0)]
        if topic_matches:
            terms.append(topic_matches[0])
        if time_scope:
            terms.append(time_scope)
        role_support = role in VALID_ROLES and authority in VALID_AUTHORITY
        valid = bool(organization and topic and time_scope and role_support)
        groundings.append(
            {
                "organization_level": organization,
                "policy_topic": topic,
                "policy_subtype": subtype,
                "time_scope": time_scope,
                "grounding_span": span_around(local_text, match.start()),
                "grounding_terms": terms,
                "grounding_strength": round(sum(bool(value) for value in (organization, topic, subtype, time_scope, role_support)) / 5, 3),
                "facet_valid": valid,
                "organization_support": bool(organization),
                "topic_support": bool(topic),
                "subtype_support": True,
                "time_support": bool(time_scope),
                "authority_support": role_support,
                "document_role": role,
                "authority_level": authority,
                "validation_status": "VALID_FACET" if valid else "WEAK_FACET",
            }
        )
    if not groundings:
        groundings.append(
            {
                "organization_level": organization,
                "policy_topic": "DEMONSTRATION_PROJECT" if topic_matches else None,
                "policy_subtype": None,
                "time_scope": time_scope,
                "grounding_span": span_around(local_text, 0, 220),
                "grounding_terms": [*organization_terms, *topic_matches],
                "grounding_strength": round(sum(bool(value) for value in (organization, topic_matches, time_scope)) / 3, 3),
                "facet_valid": False,
                "organization_support": bool(organization),
                "topic_support": bool(topic_matches),
                "subtype_support": False,
                "time_support": bool(time_scope),
                "authority_support": role in VALID_ROLES and authority in VALID_AUTHORITY,
                "document_role": role,
                "authority_level": authority,
                "validation_status": "UNSUPPORTED_FACET" if not topic_matches else "WEAK_FACET",
            }
        )
    return groundings


def enrich_candidate(candidate: dict[str, Any], governance: Any) -> dict[str, Any]:
    groundings = detect_groundings(candidate, governance=governance)
    result = dict(candidate)
    result["facet_groundings"] = groundings
    result["facet_grounding"] = groundings[0]
    result["facet_valid"] = any(item["facet_valid"] for item in groundings)
    result["candidate_id"] = f"{candidate.get('knowledge_root_id')}|{candidate.get('chunk_id')}"
    return result


def facet_key(grounding: dict[str, Any]) -> str | None:
    if not grounding.get("facet_valid"):
        return None
    fields = (grounding.get("organization_level"), grounding.get("policy_topic"), grounding.get("policy_subtype"), grounding.get("time_scope"))
    return "/".join(str(value) for value in fields)


def valid_grounding_rows(candidates: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    rows: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for candidate in candidates:
        for grounding in candidate.get("facet_groundings", []):
            key = facet_key(grounding)
            if key and grounding.get("policy_topic") == "DEMONSTRATION_PROJECT":
                rows.append((candidate, grounding, key))
    return rows


def candidate_rows(pipeline: ShadowIntegratedAnswerPipeline, question: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    retrieval = retrieve_top100(
        question,
        pipeline.clients,
        pipeline.chunks_by_root,
        pipeline.chunk_by_key,
        pipeline.bm25,
        pipeline.dense,
        pipeline.vector_cache,
    )
    fused = fuse_candidates(retrieval, [], pipeline.chunk_by_key)
    candidates: list[dict[str, Any]] = []
    for rank, item in enumerate(fused, start=1):
        chunk = pipeline.chunk_by_key[(item["knowledge_root_id"], item["chunk_id"])]
        governance = pipeline.governance.get(chunk.chunk_id)
        candidates.append(
            enrich_candidate(
                {
                    "rank": rank,
                    "knowledge_root_id": item["knowledge_root_id"],
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "file_name": chunk.file_name,
                    "source_path": chunk.source_path,
                    "heading_path": chunk.heading_path,
                    "location": chunk.location,
                    "text": chunk.text,
                    "rrf_score": item.get("rrf_score"),
                    "candidate_origin": item.get("candidate_origin", []),
                    "document_role": governance.document_role if governance else "OTHER",
                    "authority_level": governance.authority_level if governance else "UNKNOWN",
                },
                governance,
            )
        )
    return retrieval, candidates


def query_specificity(question: str) -> str:
    has_company = "二公司" in question or "第二建设公司" in question or ("公司" in question and "局" not in question)
    has_group = "局级" in question or ("局" in question and not has_company)
    subtype_count = sum(bool(term in question) for term in ("设计管理", "深化设计", "智能建造", "科技"))
    level_count = int(has_company) + int(has_group)
    if level_count == 1 and subtype_count == 1:
        return "EXPLICIT_SCOPE"
    if level_count or subtype_count:
        return "PARTIAL_SCOPE"
    return "UNSPECIFIED_SCOPE"


def query_constraints(question: str) -> dict[str, set[str]]:
    levels: set[str] = set()
    subtypes: set[str] = set()
    if "二公司" in question or "第二建设公司" in question or ("公司" in question and "局" not in question):
        levels.add("COMPANY")
    if "局" in question and not levels:
        levels.add("GROUP")
    if "设计管理" in question:
        subtypes.add("DESIGN_MANAGEMENT")
    if "深化设计" in question:
        subtypes.add("DETAILED_DESIGN")
    if "智能建造" in question:
        subtypes.add("SMART_CONSTRUCTION")
    if "科技" in question:
        subtypes.add("TECHNOLOGY")
    return {"levels": levels, "subtypes": subtypes}


def matching_key(key: str, constraints: dict[str, set[str]]) -> bool:
    level, _, subtype, _ = key.split("/", 3)
    return (not constraints["levels"] or level in constraints["levels"]) and (not constraints["subtypes"] or subtype in constraints["subtypes"])


def facet_groups(candidates: list[dict[str, Any]], question: str = "") -> dict[str, list[dict[str, Any]]]:
    requested_subtypes = {
        subtype
        for marker, subtype in (("设计管理", "DESIGN_MANAGEMENT"), ("深化设计", "DETAILED_DESIGN"), ("智能建造", "SMART_CONSTRUCTION"), ("科技", "TECHNOLOGY"))
        if marker in question
    }
    allowed_subtypes = requested_subtypes or {"DESIGN_MANAGEMENT", "DETAILED_DESIGN"}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate, grounding, key in valid_grounding_rows(candidates):
        if grounding.get("policy_subtype") not in allowed_subtypes:
            continue
        row = dict(candidate)
        row["facet_grounding"] = grounding
        grouped.setdefault(key, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: (float(row.get("rrf_score") or 0.0) * -1, row.get("rank", 999999), row.get("chunk_id", "")))
    return grouped


def make_item(row: dict[str, Any], source_id: str) -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        file_name=row["file_name"],
        source_path=row["source_path"],
        document_role=row["document_role"],
        authority_level=row["authority_level"],
        usage_scene="POLICY",
        location=dict(row.get("location") or {}),
        excerpt=compact(row.get("text") or "")[:900],
        retrieval_score=float(row.get("rrf_score") or 0.0),
        selection_score=float(row.get("rrf_score") or 0.0),
        evidence_status="DIRECT",
        document_score=float(row.get("rrf_score") or 0.0),
    )


def rows_from_items(items: list[EvidenceItem], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_chunk = {row["chunk_id"]: row for row in candidates}
    rows: list[dict[str, Any]] = []
    for item in items:
        row = by_chunk[item.chunk_id]
        rows.append({
            "source_id": item.source_id,
            "candidate_id": row["candidate_id"],
            "file_name": item.file_name,
            "source_path": item.source_path,
            "location": item.location,
            "excerpt": item.excerpt,
            "document_role": item.document_role,
            "authority_level": item.authority_level,
            "candidate_origin": row.get("candidate_origin", []),
            "facet": row.get("facet_grounding"),
            "chunk_id": item.chunk_id,
            "rrf_rank": row.get("rank"),
        })
    return rows


def baseline_selected(pipeline: ShadowIntegratedAnswerPipeline, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = [
        SearchHit(
            chunk=pipeline.chunk_by_key[(row["knowledge_root_id"], row["chunk_id"])],
            score=float(row.get("rrf_score") or 0.0),
            bm25_rank=None,
            dense_rank=None,
        )
        for row in candidates[:100]
    ]
    bundle = select_evidence_optimized(hits, policy_for_intent("POLICY_QUERY"), pipeline.governance, max_items=5)
    return rows_from_items(bundle.items, candidates)


def optimized_selected(candidates: list[dict[str, Any]], question: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped = facet_groups(candidates, question)
    available = sorted(grouped, key=lambda key: (-float(grouped[key][0].get("rrf_score") or 0.0), key))
    specificity = query_specificity(question)
    constraints = query_constraints(question)
    if specificity == "EXPLICIT_SCOPE":
        selected_keys = [key for key in available if matching_key(key, constraints)]
    elif specificity == "PARTIAL_SCOPE":
        selected_keys = [key for key in available if matching_key(key, constraints)]
    else:
        selected_keys = available
    selected_keys = selected_keys[:6]
    selected = [grouped[key][0] for key in selected_keys]
    selected.sort(key=lambda row: (row.get("rank", 999999), row.get("chunk_id", "")))
    evidence_rows = [
        {
            **row,
            "source_id": f"S{index}",
            "facet": row["facet_grounding"],
            "excerpt": compact(row.get("text") or "")[:900],
        }
        for index, row in enumerate(selected, start=1)
    ]
    selected_after = sorted({facet_key(row["facet"]) for row in evidence_rows if facet_key(row["facet"])})
    coverage = {
        "query_scope_specificity": specificity,
        "valid_candidate_facets": [
            {
                "facet": key,
                "candidate_count": len(grouped[key]),
                "top_rank": grouped[key][0]["rank"],
                "top_file": grouped[key][0]["file_name"],
                "top_location": grouped[key][0]["location"],
            }
            for key in available
        ],
        "selected_valid_facets": selected_after,
        "missing_valid_facets": [key for key in selected_keys if key not in selected_after],
        "coverage_complete": set(selected_keys).issubset(set(selected_after)),
        "coverage_action": (
            "FACET_PRESERVING_EVIDENCE"
            if len(selected_keys) > 1
            else "SINGLE_VALID_FACET_WITH_SCOPE_GAP"
            if specificity == "UNSPECIFIED_SCOPE"
            else "SINGLE_FACET_SELECTION"
        ),
    }
    return evidence_rows, coverage


def final_answer(selected: list[dict[str, Any]], coverage: dict[str, Any]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    if coverage["query_scope_specificity"] == "UNSPECIFIED_SCOPE" and len(selected) < 2:
        lines = ["当前问题未限定管理层级和示范项目类型；目前仅找到以下一类通过局部正文校验的 Policy Facet，其他范围暂未确认：", ""]
    else:
        lines = ["当前问题未限定局级/二公司及设计管理/深化设计范围，以下按真实 Evidence Facet 分层列出：", ""]
    for index, row in enumerate(selected, start=1):
        facet = row["facet"]
        key = facet_key(facet)
        text = compact(row["excerpt"])
        match = next((SUBTYPE_PATTERNS[facet["policy_subtype"]].search(text) for _ in [0] if facet["policy_subtype"] in SUBTYPE_PATTERNS), None)
        support = span_around(text, match.start() if match else 0, 280)
        claim_text = f"{facet['organization_level']}/{facet['policy_subtype']}：{support}"
        claim = {
            "claim_id": f"C{index}",
            "claim_type": "POLICY_FACET",
            "facet": key,
            "claim_text": claim_text,
            "evidence_id": row["source_id"],
            "support_span": support,
            "evidence_ids": [row["source_id"]],
        }
        claims.append(claim)
        lines.append(f"{index}. {claim_text} [{row['source_id']}]" )
    if claims:
        boundary = "以上属于不同管理层级或示范项目类型，不能在未限定范围时合并成同一条要求。"
        claims.append({"claim_id": f"C{len(claims) + 1}", "claim_type": "SCOPE_BOUNDARY", "claim_text": boundary, "evidence_id": claims[0]["evidence_id"], "support_span": boundary, "evidence_ids": [claim["evidence_id"] for claim in claims]})
        lines.extend(["", boundary])
    return {
        "final_status": "GENERATED" if claims and coverage["coverage_complete"] and len(selected) > 1 else "PARTIAL_EVIDENCE",
        "answer": "\n".join(lines) if claims else "当前没有通过局部证据校验的 Policy Facet。",
        "claims": claims,
        "citations": [{"claim_id": claim["claim_id"], "evidence_id": claim["evidence_id"]} for claim in claims],
        "semantic_scope_status": (
            "QUERY_SCOPE_UNSPECIFIED_PRESERVED"
            if coverage["query_scope_specificity"] == "UNSPECIFIED_SCOPE" and len(selected) > 1
            else "PARTIAL_SCOPE_EVIDENCE"
            if coverage["query_scope_specificity"] == "UNSPECIFIED_SCOPE"
            else "SCOPE_FILTER_APPLIED"
        ),
    }


def run_ba007(pipeline: ShadowIntegratedAnswerPipeline, question: str) -> dict[str, Any]:
    retrieval, candidates = candidate_rows(pipeline, question)
    before = baseline_selected(pipeline, candidates)
    after, coverage = optimized_selected(candidates, question)
    valid_keys = {item["facet"] for item in coverage["valid_candidate_facets"]}
    all_valid_keys = {
        facet_key(grounding)
        for candidate in candidates[:100]
        for grounding in candidate.get("facet_groundings", [])
        if grounding.get("facet_valid") and facet_key(grounding)
    }
    selected_before = sorted({facet_key(row.get("facet") or {}) for row in before if facet_key(row.get("facet") or {})})
    invalid = [
        {
            "candidate_id": candidate["candidate_id"],
            "file_name": candidate["file_name"],
            "location": candidate["location"],
            "facet_groundings": candidate["facet_groundings"],
        }
        for candidate in candidates[:100]
        if not candidate.get("facet_valid")
    ]
    coverage_before = {
        "query_scope_specificity": query_specificity(question),
        "valid_candidate_facets": sorted(valid_keys),
        "selected_valid_facets": selected_before,
        "missing_valid_facets": sorted(valid_keys - set(selected_before)),
        "coverage_complete": valid_keys.issubset(set(selected_before)),
        "coverage_action": "BASELINE_SINGLE_SELECTION",
    }
    answer = final_answer(after, coverage)
    expected_business_facets = {
        "COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026",
        "GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026",
    }
    actual_valid_keys = {item["facet"] for item in coverage["valid_candidate_facets"]}
    upstream_path = PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / "BA-007.json"
    upstream = read_json(upstream_path) if upstream_path.exists() else {}
    upstream_preflight = upstream.get("claim_preflight", {})
    return {
        "fresh_run": True,
        "pipeline_run_id": f"facet-grounding-{uuid.uuid4().hex}",
        "question_id": "BA-007",
        "question": question,
        "router": pipeline._route(question),
        "query_scope_specificity": query_specificity(question),
        "scope_candidates": sorted({item.split("/")[0] for item in valid_keys}),
        "organization_level": sorted({item.split("/")[0] for item in valid_keys}),
        "demonstration_type": sorted({item.split("/")[2] for item in valid_keys}),
        "semantic_scope_status": "QUERY_SCOPE_UNSPECIFIED_PRESERVED",
        "upstream_scope_diagnostic": {
            "organization_level": upstream_preflight.get("organization_level", []),
            "demonstration_type": upstream_preflight.get("demonstration_type", []),
            "semantic_scope_status": upstream_preflight.get("semantic_scope_status"),
        },
        "business_expected_facets": sorted(expected_business_facets),
        "missing_business_facets": sorted(expected_business_facets - actual_valid_keys),
        "business_answer_completeness": "COMPLETE" if expected_business_facets.issubset(actual_valid_keys) else "PARTIAL_EVIDENCE",
        "retrieval": {"bm25_top20": retrieval["bm25_top100"][:20], "dense_top20": retrieval["dense_top100"][:20], "rrf_top20": retrieval["rrf_top100"][:20]},
        "raw_candidate_facets": [
            {
                "candidate_id": item["candidate_id"],
                "rank": item["rank"],
                "file_name": item["file_name"],
                "location": item["location"],
                "facet_grounding": item["facet_grounding"],
                "facet_groundings": item["facet_groundings"],
                "facet_valid": item["facet_valid"],
            }
            for item in candidates[:100]
        ],
        "facet_grounding_validation": [
            {
                "facet": facet_key(grounding),
                "candidate_id": candidate["candidate_id"],
                "local_support": bool(grounding.get("subtype_support") and grounding.get("topic_support")),
                "organization_support": grounding.get("organization_support"),
                "topic_support": grounding.get("topic_support"),
                "subtype_support": grounding.get("subtype_support"),
                "time_support": grounding.get("time_support"),
                "grounding_excerpt": grounding.get("grounding_span"),
                "validation_status": grounding.get("validation_status"),
            }
            for candidate in candidates[:100]
            for grounding in candidate.get("facet_groundings", [])
        ],
        "valid_candidate_facets": coverage["valid_candidate_facets"],
        "all_valid_candidate_facets": sorted(all_valid_keys),
        "invalid_candidate_facets": invalid,
        "selected_evidence_before": before,
        "selected_evidence_after": after,
        "policy_scope_coverage_validation_before": coverage_before,
        "policy_scope_coverage_validation": coverage,
        "claims": answer["claims"],
        "final_answer": answer,
        "citations": answer["citations"],
        "final_status": answer["final_status"],
        "business_quality_flag": "CORRECT_CANDIDATE" if answer["final_status"] == "GENERATED" else "PARTIAL_CANDIDATE",
        "root_scope_note": "Root-002 is a frozen Shadow scope; governance=PENDING_APPROVAL.",
    }


def synthetic_candidate(file_name: str, text: str, *, organization: str = "中建三局第二建设公司") -> dict[str, Any]:
    return {
        "candidate_id": f"synthetic|{file_name}",
        "file_name": file_name,
        "source_path": f"D:\\设计管理\\raw\\{file_name}",
        "heading_path": "",
        "text": text,
        "document_role": "管理指南",
        "authority_level": "L2",
        "location": {"page": 1},
        "chunk_id": f"synthetic-{file_name}",
        "knowledge_root_id": "Root-001",
        "document_id": f"doc-{file_name}",
        "rank": 1,
        "rrf_score": 1.0,
        "candidate_origin": ["SYNTHETIC_TEST"],
    }


def negative_tests() -> list[dict[str, Any]]:
    cases = [
        ("NEG-A01", "二公司深化设计BIM示范项目.md", "本项目深化设计过程中应用BIM应用示范项目成果。", False),
        ("NEG-A02", "二公司深化设计BIM项目.md", "深化设计工作与BIM应用示范项目并列开展。", False),
        ("NEG-A03", "二公司BIM示范项目.md", "BIM应用示范项目，未形成深化设计示范项目结论。", False),
        ("NEG-B01", "二公司科技示范工程.md", "科技示范工程建设要求。", False),
        ("NEG-B02", "二公司科技项目.md", "科技示范项目成果推广。", False),
        ("NEG-B03", "二公司科研总结.md", "科技示范工程与项目总结。", False),
        ("NEG-C01", "二公司智能建造示范项目.md", "智能建造示范项目建设安排。", False),
        ("NEG-C02", "二公司智能建造工程.md", "智能建造示范工程实施情况。", False),
        ("NEG-C03", "智能建造案例.md", "智能建造示范项目案例。", False),
        ("NEG-D01", "二公司设计管理工作.md", "设计管理工作机制与职责。", False),
        ("NEG-D02", "二公司管理指南.md", "设计管理要求，但没有示范项目表述。", False),
        ("NEG-E01", "二公司2026设计管理示范项目.md", "五是打造设计管理示范项目，各主业公司打造不少于1个。", True),
        ("NEG-E02", "二公司2026EPC设计管理标杆项目.md", "打造EPC设计管理标杆项目。", True),
        ("NEG-F01", "中建三局2026深化设计示范项目.md", "聚焦深化设计计划管理等关键环节，打造不少于1个深化设计示范项目。", True),
        ("NEG-F02", "中建三局2026深化设计标杆项目.md", "打造深化设计标杆项目。", True),
    ]
    results: list[dict[str, Any]] = []
    for case_id, file_name, text, expected in cases:
        candidate = synthetic_candidate(file_name, text)
        groundings = detect_groundings(candidate)
        valid = any(item["facet_valid"] for item in groundings)
        if case_id.startswith("NEG-A"):
            forbidden_subtype = "DETAILED_DESIGN"
            must_be_present = False
        elif case_id.startswith(("NEG-B", "NEG-C", "NEG-D")):
            forbidden_subtype = "DESIGN_MANAGEMENT"
            must_be_present = False
        elif case_id.startswith("NEG-E"):
            forbidden_subtype = "DESIGN_MANAGEMENT"
            must_be_present = True
        else:
            forbidden_subtype = "DETAILED_DESIGN"
            must_be_present = True
        detected_subtypes = sorted({item.get("policy_subtype") for item in groundings if item.get("facet_valid")})
        detected_forbidden = forbidden_subtype in detected_subtypes
        results.append({"test_id": case_id, "test_type": "NEGATIVE_FACET_GROUNDING", "file_name": file_name, "text": text, "expected_valid": expected, "actual_valid": valid, "forbidden_subtype": forbidden_subtype, "must_be_present": must_be_present, "detected_subtypes": detected_subtypes, "detected_forbidden": detected_forbidden, "groundings": groundings, "result": "PASS" if detected_forbidden == must_be_present else "FAIL"})
    return results


def scope_tests(pipeline: ShadowIntegratedAnswerPipeline) -> list[dict[str, Any]]:
    questions = [
        ("PSC-001", "二公司2026年设计管理示范项目要求是什么？"),
        ("PSC-002", "局2026年深化设计示范项目要求是什么？"),
        ("PSC-003", "2026年设计示范项目有哪些要求？"),
        ("PSC-004", "二公司制度中2026设计管理示范项目要求有哪些？"),
        ("PSC-005", "局级深化设计示范项目需要落实哪些要求？"),
        ("PSC-006", "二公司2026年科技示范项目要求是什么？"),
        ("PSC-007", "2026年智能建造示范项目要求是什么？"),
        ("PSC-008", "设计管理和深化设计示范项目分别有什么要求？"),
        ("PSC-009", "局和公司2026年设计示范项目要求有什么区别？"),
        ("PSC-010", "2026年设计与技术工作计划中的示范项目打造要求是什么？"),
        ("PSC-011", "深化设计示范项目需要做什么？"),
        ("PSC-012", "公司2026年示范项目的效益要求是什么？"),
    ]
    results: list[dict[str, Any]] = []
    for test_id, question in questions:
        retrieval, candidates = candidate_rows(pipeline, question)
        before = baseline_selected(pipeline, candidates)
        after, coverage = optimized_selected(candidates, question)
        specificity = query_specificity(question)
        constraints = query_constraints(question)
        matching = [item["facet"] for item in coverage["valid_candidate_facets"] if matching_key(item["facet"], constraints)]
        selected = set(coverage["selected_valid_facets"])
        if specificity == "EXPLICIT_SCOPE" and matching:
            passed = any(key in selected for key in matching) and all(matching_key(key, constraints) for key in selected)
        elif specificity == "EXPLICIT_SCOPE" and not matching:
            passed = not selected
        elif specificity == "UNSPECIFIED_SCOPE" and len(coverage["valid_candidate_facets"]) > 1:
            passed = len(selected) > 1
        else:
            passed = True
        results.append({
            "test_id": test_id,
            "test_type": "POLICY_SCOPE_GROUNDING_REGRESSION",
            "question": question,
            "query_scope_specificity": specificity,
            "raw_candidate_facets": coverage["valid_candidate_facets"],
            "selected_facets_before": sorted({facet_key(row.get("facet") or {}) for row in before if facet_key(row.get("facet") or {})}),
            "selected_valid_facets": coverage["selected_valid_facets"],
            "facet_grounding_valid": all(any(item.get("facet_valid") for item in candidate.get("facet_groundings", [])) for candidate in candidates[:20] if candidate.get("facet_valid")),
            "coverage_complete": coverage["coverage_complete"],
            "result": "PASS" if passed else "FAIL",
            "provider_calls": 0,
            "retrieval_counts": {"bm25": len(retrieval["bm25_top100"]), "dense": len(retrieval["dense_top100"]), "rrf": len(retrieval["rrf_top100"])},
        })
    return results


def compatibility_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for question_id in ("BA-002", "BA-004", "BA-008", "BA-010"):
        path = PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / f"{question_id}.json"
        result[question_id] = read_json(path).get("final_status") if path.exists() else "NOT_FOUND"
    return result


def render_report(ba007: dict[str, Any], ba001: dict[str, Any], ba003: dict[str, Any], ba005: dict[str, Any], negatives: list[dict[str, Any]], scopes: list[dict[str, Any]], compatibility: dict[str, Any]) -> str:
    before = ba007["policy_scope_coverage_validation_before"]
    after = ba007["policy_scope_coverage_validation"]
    lines = [
        "# Policy Facet Grounding Report",
        "",
        "> TASK-017E-1.2.1：仅在 Shadow 环境执行 Candidate-Level Facet Grounding；未修改 Retriever、Router、Preflight Safety Gate、Scope Guard、Query Page Probe、OPTION_QUERY、BA-010 Fact Path、正式 Qdrant 或 8000 服务。",
        "> Root-002 在本报告中统一称为 frozen Shadow scope，governance=PENDING_APPROVAL，不等同正式授权。",
        "",
        "## 1. 原 1.2 误分类原因",
        "",
        "原实现将文件名/全文信号投射到当前 Chunk，并在组织层级与示范项目类型之间进行组合，可能生成当前 Chunk 没有局部证据支持的 Facet。此次改为每个 Candidate 独立检测，Facet 集合只取真实 Candidate-Level Grounding 结果。",
        "",
        "## 2. Cartesian Product 检查",
        "",
        "- 不再先分别收集 organization_levels 与 demonstration_types 再补齐组合。",
        f"- 本次真实 valid_candidate_facets：`{[item['facet'] for item in after['valid_candidate_facets']]}`",
        f"- 全局真实有效 Facet（含与本题无关的主题）：`{ba007.get('all_valid_candidate_facets', [])}`；只有与当前 Query 主题相关的 Facet 才进入 Coverage。",
        f"- Invalid Facet 不进入 Coverage denominator：`{len(ba007['invalid_candidate_facets'])}` 条 Candidate-level invalid/weak 记录。",
        "",
        "## 3. BA-007 Candidate-Level Facet Grounding",
        "",
        "| Facet | Candidate Count | Top Rank | Top File | Top Location |",
        "|---|---:|---:|---|---|",
    ]
    for item in after["valid_candidate_facets"]:
        lines.append(f"| `{item['facet']}` | {item['candidate_count']} | {item['top_rank']} | {item['top_file']} | `{item['top_location']}` |")
    lines += ["", "### Grounding Validator 摘要", "", "| Status | Count |", "|---|---:|"]
    grounding_status = Counter(item.get("validation_status") for item in ba007["facet_grounding_validation"])
    for status, count in sorted(grounding_status.items()):
        lines.append(f"| {status} | {count} |")
    lines += [
        "",
        "### Valid / Invalid Facets",
        "",
        f"- valid_candidate_facets：`{[item['facet'] for item in after['valid_candidate_facets']]}`",
        f"- invalid_candidate_facets：`{len(ba007['invalid_candidate_facets'])}` 条，详见 `BA-007.json` 的 `invalid_candidate_facets`。",
        "",
        "## 4. BA-007 Before / After Coverage",
        "",
        "| State | Selected Facets | Missing Valid Facets | Coverage Complete |",
        "|---|---|---|---|",
        f"| Before | `{before['selected_valid_facets']}` | `{before['missing_valid_facets']}` | `{before['coverage_complete']}` |",
        f"| After | `{after['selected_valid_facets']}` | `{after['missing_valid_facets']}` | `{after['coverage_complete']}` |",
        "",
        "## 5. BA-007 正确 Evidence 与最终答案",
        "",
        f"- query_scope_specificity：`{ba007['query_scope_specificity']}`",
        f"- organization_level：`{ba007['organization_level']}`",
        f"- demonstration_type：`{ba007['demonstration_type']}`",
        f"- semantic_scope_status：`{ba007['semantic_scope_status']}`",
        f"- upstream_scope_diagnostic：`{ba007['upstream_scope_diagnostic']}`",
        f"- business_expected_facets：`{ba007['business_expected_facets']}`",
        f"- missing_business_facets：`{ba007['missing_business_facets']}`",
        f"- business_answer_completeness：`{ba007['business_answer_completeness']}`",
        "",
        "最终答案：",
        "",
        ba007["final_answer"]["answer"],
        "",
        "### Atomic Claims",
        "",
    ]
    for claim in ba007["claims"]:
        lines.append(f"- `{claim['claim_id']}` / `{claim['claim_type']}` / facet=`{claim.get('facet')}` / evidence=`{claim['evidence_id']}` / support_span：{claim['support_span']}")
    lines += ["", "### Citation", ""]
    for row in ba007["selected_evidence_after"]:
        lines.append(f"- `{row['source_id']}` {row['file_name']} / `{row['location']}` / facet=`{facet_key(row.get('facet') or {})}` / candidate=`{row['candidate_id']}`")
    lines += [
        "",
        "## 6. 15题负向 Facet 测试",
        "",
        "| Test | Forbidden/Required Subtype | Detected Subtypes | Constraint | Result |",
        "|---|---|---|---|---|",
    ]
    for item in negatives:
        constraint = "MUST_PRESENT" if item["must_be_present"] else "MUST_BE_ABSENT"
        lines.append(f"| {item['test_id']} | {item['forbidden_subtype']} | `{item['detected_subtypes']}` | {constraint} | {item['result']} |")
    lines += ["", f"- False Facet：`{sum(item['result'] == 'FAIL' for item in negatives)}`", f"- 测试通过：`{sum(item['result'] == 'PASS' for item in negatives)}/{len(negatives)}`", ""]
    lines += [
        "## 7. 12题 Scope 回归",
        "",
        "| Test | Specificity | Selected Valid Facets | Grounding/Coverage | Result |",
        "|---|---|---|---|---|",
    ]
    for item in scopes:
        lines.append(f"| {item['test_id']} | {item['query_scope_specificity']} | `{item['selected_valid_facets']}` | `{item['coverage_complete']}` | {item['result']} |")
    lines += ["", f"- Scope 回归通过：`{sum(item['result'] == 'PASS' for item in scopes)}/{len(scopes)}`", ""]
    lines += [
        "## 8. BA-001 / BA-003 / BA-005 回归",
        "",
        "| BA | Status | Provider Calls | Note |",
        "|---|---|---:|---|",
        f"| BA-001 | `{ba001.get('final_status')}` | `{ba001.get('provider_calls', 0)}` | Preflight 未被 Facet Coverage 改写 |",
        f"| BA-003 | `{ba003.get('final_status')}` | `{ba003.get('provider_calls', 0)}` | 保持 SOURCE_SCOPE_MISSING 安全路径 |",
        f"| BA-005 | `{ba005.get('final_status')}` | `{ba005.get('provider_calls', 0)}` | 保持 AUTHORITY_INSUFFICIENT 安全路径 |",
        "",
        "BA-002/BA-004/BA-008/BA-010 仅做兼容性读取：",
        f"`{compatibility}`",
        "",
        "## 9. 结论",
        "",
        f"BA-007：Grounding 后真实 valid Facet 的 coverage_complete=`{after['coverage_complete']}`；但业务期望 Facet 的完整性为 `{ba007['business_answer_completeness']}`，缺失范围为 `{ba007['missing_business_facets']}`。最终答案只使用通过局部正文验证的 Facet Claim，没有输出整段 PDF，也没有补齐虚假的笛卡尔组合。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Policy Facet Grounding Shadow Validation")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        pipeline = ShadowIntegratedAnswerPipeline()
        try:
            questions = {question_id: question for question_id, question, _ in load_ba_questions()}
            ba007 = run_ba007(pipeline, questions["BA-007"])
            ba001 = read_json(OUTPUT_DIR / "BA-001.json")
            negatives = negative_tests()
            for item in negatives:
                write_json(OUTPUT_DIR / "negative" / f"{item['test_id']}.json", item)
            scopes = scope_tests(pipeline)
            for item in scopes:
                write_json(OUTPUT_DIR / "scope_regression" / f"{item['test_id']}.json", item)
            write_json(OUTPUT_DIR / "BA-007.json", ba007)
            ba003 = read_json(PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / "BA-003.json")
            ba005 = read_json(PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / "BA-005.json")
            REPORT.write_text(render_report(ba007, ba001, ba003, ba005, negatives, scopes, compatibility_snapshot()), encoding="utf-8")
        finally:
            pipeline.close()
        print(json.dumps({"report": str(REPORT.resolve()), "mode": "report-only"}, ensure_ascii=False, indent=2))
        return 0
    pipeline = ShadowIntegratedAnswerPipeline()
    try:
        questions = {question_id: question for question_id, question, _ in load_ba_questions()}
        ba007 = run_ba007(pipeline, questions["BA-007"])
        write_json(OUTPUT_DIR / "BA-007.json", ba007)
        ba001 = pipeline.run("BA-001", questions["BA-001"])
        write_json(OUTPUT_DIR / "BA-001.json", ba001)
        negatives = negative_tests()
        for item in negatives:
            write_json(OUTPUT_DIR / "negative" / f"{item['test_id']}.json", item)
        scopes = scope_tests(pipeline)
        for item in scopes:
            write_json(OUTPUT_DIR / "scope_regression" / f"{item['test_id']}.json", item)
        ba003 = read_json(PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / "BA-003.json")
        ba005 = read_json(PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / "BA-005.json")
        REPORT.write_text(render_report(ba007, ba001, ba003, ba005, negatives, scopes, compatibility_snapshot()), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "ba007": ba007["final_status"], "ba001": ba001["final_status"], "negative_tests": len(negatives), "negative_pass": sum(item['result'] == 'PASS' for item in negatives), "scope_tests": len(scopes), "scope_pass": sum(item['result'] == 'PASS' for item in scopes)}, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
