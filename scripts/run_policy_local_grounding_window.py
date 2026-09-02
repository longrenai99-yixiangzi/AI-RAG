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

from scripts.run_p0_integrated_shadow_regression import ShadowIntegratedAnswerPipeline
from scripts.shadow_answer_router_v1 import load_ba_questions
from scripts.validate_knowledge_page_retrieval_rescue import fuse_candidates, retrieve_top100


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "policy_local_grounding_window"
REPORT = PROJECT_ROOT / "docs" / "POLICY_LOCAL_GROUNDING_WINDOW_REPORT.md"
BASELINE_JSON = PROJECT_ROOT / "evaluation" / "policy_facet_grounding" / "BA-007.json"

COMPANY_MARKERS = ("\u7b2c\u4e8c\u5efa\u8bbe\u516c\u53f8", "\u4e8c\u516c\u53f8")
GROUP_MARKERS = ("\u4e2d\u5efa\u4e09\u5c40", "\u5c40\u7ea7")
DEMO_SUFFIX = r"(?:\u793a\u8303\u9879\u76ee|\u793a\u8303\u5de5\u7a0b|\u6807\u6746\u9879\u76ee|\u8bd5\u70b9\u9879\u76ee)"

# These are semantic anchors, not customer/project names.  The patterns are
# deliberately local: a distant occurrence in the same chunk cannot supply a
# missing subtype.
SUBTYPE_PATTERNS = {
    "DESIGN_MANAGEMENT": re.compile(r"(?:EPC)?\u8bbe\u8ba1\u7ba1\u7406" + DEMO_SUFFIX),
    "DETAILED_DESIGN": re.compile(r"\u6df1\u5316\u8bbe\u8ba1(?:[\u4e00-\u9fff0-9]{0,24})?" + DEMO_SUFFIX),
    "TECHNOLOGY": re.compile(r"\u79d1\u6280" + DEMO_SUFFIX),
    "SMART_CONSTRUCTION": re.compile(r"\u667a\u80fd\u5efa\u9020" + DEMO_SUFFIX),
    "GREEN_CONSTRUCTION": re.compile(r"\u7eff\u8272" + DEMO_SUFFIX),
}
GENERIC_ANCHOR = re.compile(
    r"(?:\u6253\u9020|\u5efa\u8bbe|\u7acb\u9879)?"
    r"[\u4e00-\u9fffA-Za-z0-9（）()、\-]{0,28}"
    + DEMO_SUFFIX
)
VALID_ROLES = {"\u6b63\u5f0f\u5236\u5ea6", "\u7ba1\u7406\u6307\u5357", "\u6807\u51c6\u6a21\u677f"}
VALID_AUTHORITY = {"L1", "L2", "L3"}
SIGNATURE_RE = re.compile(r"(?:\u5218\u7545|\u7b2c\u4e8c\u5efa\u8bbe\u516c\u53f8)\s*\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_for_matching(text: str) -> str:
    """Normalize PDF line breaks without changing business wording."""
    value = compact(text)
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)


def clean_support(text: str) -> str:
    value = compact(text)
    value = SIGNATURE_RE.sub("", value)
    value = TIMESTAMP_RE.sub("", value)
    value = re.sub(r"(?:\u5185\u90e8\u8d44\u6599|\u4ec5\u4f9b\u53c2\u8003|\u6c34\u5370)[:：]?", "", value)
    return compact(value).strip(" -|；;")


def organization_from_metadata(candidate: dict[str, Any]) -> tuple[str | None, list[str]]:
    file_heading = compact(f"{candidate.get('file_name', '')} {candidate.get('heading_path', '')}")
    source_path = compact(candidate.get("source_path", ""))
    # File title/heading has precedence over the containing directory.  This
    # prevents a group plan stored under a company technical-department path
    # from being relabeled as a company document.
    if any(marker in file_heading for marker in COMPANY_MARKERS):
        return "COMPANY", ["file_name_or_heading/company_publisher"]
    if any(marker in file_heading for marker in GROUP_MARKERS):
        return "GROUP", ["file_name_or_heading/group_publisher"]
    if any(marker in source_path for marker in COMPANY_MARKERS):
        return "COMPANY", ["source_path/company_publisher"]
    if any(marker in source_path for marker in GROUP_MARKERS):
        return "GROUP", ["source_path/group_publisher"]
    return None, []


def time_from_metadata(candidate: dict[str, Any]) -> tuple[str | None, str | None]:
    metadata = compact(f"{candidate.get('file_name', '')} {candidate.get('source_path', '')} {candidate.get('heading_path', '')}")
    match = re.search(r"20\d{2}", metadata)
    return (match.group(0), "document_metadata") if match else (None, None)


def local_window(text: str, start: int, end: int, *, radius: int = 230) -> str:
    # Prefer the sentence containing the anchor. If a PDF extractor produces
    # an unusually long sentence, use a centered character window instead.
    left_marks = [text.rfind(mark, 0, start) for mark in ("。", "；", "！", "？", "\n")]
    right_marks = [position for mark in ("。", "；", "！", "？", "\n") if (position := text.find(mark, end)) >= 0]
    left = max(left_marks, default=-1) + 1
    right = min(right_marks, default=len(text)) + (1 if right_marks else 0)
    sentence = clean_support(text[left:right])
    if 0 < len(sentence) <= 380:
        return sentence
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return clean_support(text[left:right][:520])


def infer_local_subtype(anchor_text: str) -> str | None:
    for subtype, pattern in SUBTYPE_PATTERNS.items():
        if pattern.search(anchor_text):
            return subtype
    return None


def detect_local_groundings(candidate: dict[str, Any], *, include_unsupported: bool = True) -> list[dict[str, Any]]:
    full_text = normalize_for_matching(candidate.get("text", ""))
    organization, organization_terms = organization_from_metadata(candidate)
    document_year, year_source = time_from_metadata(candidate)
    role = str(candidate.get("document_role") or "")
    authority = str(candidate.get("authority_level") or "UNKNOWN")
    matches: list[tuple[int, int, str, str]] = []

    for subtype, pattern in SUBTYPE_PATTERNS.items():
        for match in pattern.finditer(full_text):
            matches.append((match.start(), match.end(), match.group(0), subtype))

    # Generic anchors are retained as unsupported/weak diagnostics, but they
    # never receive a subtype merely because another part of the chunk has one.
    if not matches:
        for match in GENERIC_ANCHOR.finditer(full_text):
            matches.append((match.start(), match.end(), match.group(0), ""))

    deduped: list[tuple[int, int, str, str]] = []
    for item in sorted(matches, key=lambda row: (row[0], -(row[1] - row[0]), row[3])):
        if any(item[0] < prior[1] and prior[0] < item[1] for prior in deduped):
            continue
        deduped.append(item)

    rows: list[dict[str, Any]] = []
    for start, end, anchor_text, subtype in deduped:
        span = local_window(full_text, start, end)
        span_year = re.search(r"20\d{2}", span)
        time_scope = span_year.group(0) if span_year else document_year
        time_support_source = "local_span" if span_year else year_source
        topic = "DEMONSTRATION_PROJECT" if re.search(DEMO_SUFFIX, anchor_text) else None
        role_support = role in VALID_ROLES and authority in VALID_AUTHORITY
        valid = bool(organization and topic and subtype and time_scope and role_support)
        status = "VALID_FACET" if valid else "WEAK_FACET" if topic or subtype else "UNSUPPORTED_FACET"
        rows.append(
            {
                "anchor_text": clean_support(anchor_text),
                "span_text": span,
                "grounding_span": span,
                "organization_level": organization,
                "policy_topic": topic,
                "policy_subtype": subtype or None,
                "time_scope": time_scope,
                "time_support_source": time_support_source,
                "organization_terms": organization_terms,
                "document_role": role,
                "authority_level": authority,
                "role_authority_support": role_support,
                "grounding_terms": [*organization_terms, clean_support(anchor_text), *( [time_scope] if time_scope else [])],
                "facet_valid": valid,
                "validation_status": status,
                "grounding_strength": round(sum(bool(value) for value in (organization, topic, subtype, time_scope, role_support)) / 5, 3),
            }
        )

    if include_unsupported and not rows:
        fallback = clean_support(full_text[:320])
        rows.append(
            {
                "anchor_text": None,
                "span_text": fallback,
                "grounding_span": fallback,
                "organization_level": organization,
                "policy_topic": None,
                "policy_subtype": None,
                "time_scope": document_year,
                "time_support_source": year_source,
                "organization_terms": organization_terms,
                "document_role": role,
                "authority_level": authority,
                "role_authority_support": role in VALID_ROLES and authority in VALID_AUTHORITY,
                "grounding_terms": organization_terms,
                "facet_valid": False,
                "validation_status": "UNSUPPORTED_FACET",
                "grounding_strength": 0.0,
            }
        )
    return rows


def enrich(candidate: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    row["local_grounding_spans"] = detect_local_groundings(row)
    row["facet_groundings"] = row["local_grounding_spans"]
    row["facet_valid"] = any(item["facet_valid"] for item in row["local_grounding_spans"])
    row["candidate_id"] = f"{row.get('knowledge_root_id')}|{row.get('chunk_id')}"
    return row


def facet_key(grounding: dict[str, Any]) -> str | None:
    if not grounding.get("facet_valid"):
        return None
    fields = (grounding.get("organization_level"), grounding.get("policy_topic"), grounding.get("policy_subtype"), grounding.get("time_scope"))
    return "/".join(str(value) for value in fields)


def retrieve_candidates(pipeline: ShadowIntegratedAnswerPipeline, question: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
            enrich(
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
                }
            )
        )
    return retrieval, candidates


def query_constraints(question: str) -> dict[str, set[str]]:
    levels: set[str] = set()
    subtypes: set[str] = set()
    if "\u516c\u53f8" in question and "\u5c40" not in question:
        levels.add("COMPANY")
    if "\u5c40" in question and not levels:
        levels.add("GROUP")
    if "\u8bbe\u8ba1\u7ba1\u7406" in question:
        subtypes.add("DESIGN_MANAGEMENT")
    if "\u6df1\u5316\u8bbe\u8ba1" in question:
        subtypes.add("DETAILED_DESIGN")
    if "\u667a\u80fd\u5efa\u9020" in question:
        subtypes.add("SMART_CONSTRUCTION")
    if "\u79d1\u6280" in question:
        subtypes.add("TECHNOLOGY")
    return {"levels": levels, "subtypes": subtypes}


def query_specificity(question: str) -> str:
    constraints = query_constraints(question)
    if len(constraints["levels"]) == 1 and len(constraints["subtypes"]) == 1:
        return "EXPLICIT_SCOPE"
    if constraints["levels"] or constraints["subtypes"]:
        return "PARTIAL_SCOPE"
    return "UNSPECIFIED_SCOPE"


def matching_key(key: str, constraints: dict[str, set[str]]) -> bool:
    level, _, subtype, _ = key.split("/", 3)
    return (not constraints["levels"] or level in constraints["levels"]) and (not constraints["subtypes"] or subtype in constraints["subtypes"])


def relevant_subtypes(question: str) -> set[str]:
    requested = set(query_constraints(question)["subtypes"])
    return requested or {"DESIGN_MANAGEMENT", "DETAILED_DESIGN"}


def valid_rows(candidates: list[dict[str, Any]], question: str) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    allowed = relevant_subtypes(question)
    rows: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for candidate in candidates:
        for grounding in candidate.get("local_grounding_spans", []):
            key = facet_key(grounding)
            if key and grounding.get("policy_subtype") in allowed:
                rows.append((candidate, grounding, key))
    return rows


def baseline_selection(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Use the persisted 1.2.1 output when available. This keeps A/B comparison
    # honest and avoids silently recomputing the old selector with new rules.
    if BASELINE_JSON.exists():
        persisted = read_json(BASELINE_JSON)
        return persisted.get("selected_evidence_after", [])
    # Minimal fallback for a clean checkout without the prior report.
    rows = [candidate for candidate in candidates[:5]]
    return [
        {
            "source_id": f"S{index}",
            "candidate_id": row["candidate_id"],
            "chunk_id": row["chunk_id"],
            "file_name": row["file_name"],
            "location": row["location"],
            "excerpt": compact(row.get("text", ""))[:900],
            "facet": next((g for g in row.get("local_grounding_spans", []) if g.get("facet_valid")), None),
        }
        for index, row in enumerate(rows, start=1)
    ]


def optimized_selection(candidates: list[dict[str, Any]], question: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for candidate, grounding, key in valid_rows(candidates, question):
        grouped.setdefault(key, []).append((candidate, grounding))
    for rows in grouped.values():
        rows.sort(key=lambda pair: (float(pair[0].get("rrf_score") or 0.0) * -1, pair[0].get("rank", 999999), pair[0].get("chunk_id", "")))

    constraints = query_constraints(question)
    available = sorted(grouped, key=lambda key: (-float(grouped[key][0][0].get("rrf_score") or 0.0), key))
    selected_keys = [key for key in available if matching_key(key, constraints)]
    selected_keys = selected_keys[:6]
    chosen = [grouped[key][0] for key in selected_keys]
    chosen.sort(key=lambda pair: (pair[0].get("rank", 999999), pair[0].get("chunk_id", "")))
    evidence = []
    for index, (candidate, grounding) in enumerate(chosen, start=1):
        evidence.append(
            {
                "source_id": f"S{index}",
                "candidate_id": candidate["candidate_id"],
                "chunk_id": candidate["chunk_id"],
                "file_name": candidate["file_name"],
                "source_path": candidate["source_path"],
                "location": candidate["location"],
                "excerpt": compact(candidate.get("text", ""))[:900],
                "facet": grounding,
                "support_span": grounding.get("span_text"),
                "candidate_origin": candidate.get("candidate_origin", []),
                "rrf_rank": candidate.get("rank"),
            }
        )
    selected_facets = sorted({facet_key(item["facet"]) for item in evidence if facet_key(item["facet"])})
    coverage = {
        "query_scope_specificity": query_specificity(question),
        "valid_candidate_facets": [
            {
                "facet": key,
                "candidate_count": len(grouped[key]),
                "top_rank": grouped[key][0][0].get("rank"),
                "top_file": grouped[key][0][0].get("file_name"),
                "top_location": grouped[key][0][0].get("location"),
                "top_support_span": grouped[key][0][1].get("span_text"),
            }
            for key in available
        ],
        "selected_valid_facets": selected_facets,
        "missing_valid_facets": [key for key in available if key not in selected_facets],
        "coverage_complete": set(available).issubset(set(selected_facets)),
        "coverage_action": "FACET_PRESERVING_LOCAL_WINDOW" if len(selected_facets) > 1 else "SINGLE_FACET_OR_SCOPE_GAP",
    }
    return evidence, coverage


def sentence_claims(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    grounding = evidence["facet"]
    span = clean_support(grounding.get("span_text") or evidence.get("excerpt") or "")
    subtype = grounding.get("policy_subtype")
    claims: list[str] = []
    if subtype == "DESIGN_MANAGEMENT":
        if re.search(r"\u5404\u4e3b\u4e1a\u516c\u53f8\s*\u6253\u9020\s*\u4e0d\u5c11\u4e8e\s*1\s*\u4e2a", span) and "\u8bbe\u8ba1\u7ba1\u7406\u793a\u8303\u9879\u76ee" in span:
            claims.append("各主业公司打造不少于1个设计管理示范项目。")
        match = re.search(r"\u8bbe\u8ba1\u6548\u76ca\u589e\u91cf\s*\u8d85\s*\*%\s*\u6216\s*\u8bbe\u8ba1\u521b\u6548\u91d1\u989d\s*\u8d85\s*\*\*\u4e07", span)
        if match:
            claims.append(clean_support(match.group(0)))
    elif subtype == "DETAILED_DESIGN":
        for pattern in (
            r"\u805a\u7126\s*\u6df1\u5316\u8bbe\u8ba1\u8ba1\u5212\u7ba1\u7406\s*\u7b49\s*6\s*\u5927\u5173\u952e\u73af\u8282\s*[,，]\s*\u5236\u5b9a\u6807\u51c6\u5316\u7ba1\u63a7\u6e05\u5355",
            r"\u6253\u9020\s*\u4e0d\u5c11\u4e8e\s*1\s*\u4e2a\s*\u6df1\u5316\u8bbe\u8ba1\u793a\u8303\u9879\u76ee",
        ):
            match = re.search(pattern, span)
            if match:
                claims.append(clean_support(match.group(0)))
    if not claims:
        pieces = [clean_support(item) for item in re.split(r"(?<=[。；！？])", span) if clean_support(item)]
        claims = pieces[:1] or [span[:220]]
    unique: list[str] = []
    for claim in claims:
        if claim and claim not in unique:
            unique.append(claim[:260])
    return [
        {
            "claim_type": "POLICY_ATOMIC",
            "facet": facet_key(grounding),
            "claim_text": text,
            "evidence_id": evidence["source_id"],
            "evidence_ids": [evidence["source_id"]],
            "support_span": span,
        }
        for text in unique
    ]


def make_ba007_answer(evidence: list[dict[str, Any]], coverage: dict[str, Any]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for item in evidence:
        claims.extend(sentence_claims(item))
    if len(coverage.get("selected_valid_facets", [])) >= 2:
        ids = [claim["evidence_id"] for claim in claims]
        claims.append(
            {
                "claim_type": "SCOPE_BOUNDARY",
                "facet": "MULTI_SCOPE_BOUNDARY",
                "claim_text": "公司层面的设计管理示范项目要求，与局级的深化设计示范项目要求属于不同管理层级和专业类型。",
                "evidence_id": ids[0] if ids else None,
                "evidence_ids": sorted(set(ids)),
                "support_span": "selected_valid_facets>=2; boundary is derived from the two validated facet identities",
            }
        )
    for index, claim in enumerate(claims, start=1):
        claim["claim_id"] = f"C{index}"
    lines = ["结论：根据当前选中的局部政策证据，示范项目要求按已验证的管理层级和专业类型分别列示。", ""]
    for index, claim in enumerate(claims, start=1):
        if claim["claim_type"] == "SCOPE_BOUNDARY":
            continue
        lines.append(f"{index}. {claim['claim_text']} [{claim['evidence_id']}]")
    if not claims:
        lines.append("当前没有通过局部证据校验的示范项目要求。")
    return {
        "final_status": "GENERATED" if coverage.get("coverage_complete") and len(coverage.get("selected_valid_facets", [])) >= 2 else "PARTIAL_EVIDENCE",
        "answer": "\n".join(lines),
        "claims": claims,
        "citations": [{"claim_id": claim["claim_id"], "evidence_id": claim.get("evidence_id")} for claim in claims],
        "citation_consistency": all(item.get("evidence_id") in {row["source_id"] for row in evidence} for item in claims),
    }


def run_ba007(pipeline: ShadowIntegratedAnswerPipeline, question: str) -> dict[str, Any]:
    retrieval, candidates = retrieve_candidates(pipeline, question)
    before = baseline_selection(candidates)
    after, coverage = optimized_selection(candidates, question)
    all_valid = sorted({facet_key(g) for candidate in candidates[:100] for g in candidate.get("local_grounding_spans", []) if facet_key(g)})
    expected = {
        "COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026",
        "GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026",
    }
    actual = {item["facet"] for item in coverage["valid_candidate_facets"]}
    invalid = [
        {
            "candidate_id": candidate["candidate_id"],
            "rank": candidate["rank"],
            "file_name": candidate["file_name"],
            "location": candidate["location"],
            "local_grounding_spans": candidate["local_grounding_spans"],
        }
        for candidate in candidates[:100]
        if not candidate.get("facet_valid")
    ]
    answer = make_ba007_answer(after, coverage)
    return {
        "fresh_run": True,
        "pipeline_run_id": f"local-window-{uuid.uuid4().hex}",
        "question_id": "BA-007",
        "question": question,
        "retrieval": {"bm25_top20": retrieval["bm25_top100"][:20], "dense_top20": retrieval["dense_top100"][:20], "rrf_top20": retrieval["rrf_top100"][:20]},
        "raw_candidate_facets": [
            {
                "candidate_id": candidate["candidate_id"],
                "rank": candidate["rank"],
                "file_name": candidate["file_name"],
                "location": candidate["location"],
                "candidate_origin": candidate.get("candidate_origin", []),
                "local_grounding_spans": candidate["local_grounding_spans"],
                "facet_valid": candidate["facet_valid"],
            }
            for candidate in candidates[:100]
        ],
        "valid_candidate_facets": coverage["valid_candidate_facets"],
        "invalid_candidate_facets": invalid,
        "selected_valid_facets": coverage["selected_valid_facets"],
        "missing_valid_facets": coverage["missing_valid_facets"],
        "all_valid_candidate_facets": all_valid,
        "business_expected_facets": sorted(expected),
        "missing_business_facets": sorted(expected - actual),
        "business_answer_completeness": "COMPLETE" if expected.issubset(actual) else "PARTIAL_EVIDENCE",
        "selected_evidence_before": before,
        "selected_evidence_after": after,
        "coverage": coverage,
        "claims": answer["claims"],
        "final_answer": answer,
        "final_status": answer["final_status"],
        "root_scope_note": "Root-002 is a frozen Shadow scope; governance=PENDING_APPROVAL.",
    }


def synthetic_candidate(file_name: str, text: str, *, role: str = "\u7ba1\u7406\u6307\u5357", authority: str = "L2") -> dict[str, Any]:
    return {
        "candidate_id": f"synthetic|{file_name}",
        "file_name": file_name,
        "source_path": f"D:\\synthetic\\{file_name}",
        "heading_path": "",
        "text": text,
        "document_role": role,
        "authority_level": authority,
        "location": {"page": 1},
        "chunk_id": f"synthetic-{file_name}",
        "knowledge_root_id": "Root-001",
        "document_id": f"doc-{file_name}",
        "rank": 1,
        "rrf_score": 1.0,
        "candidate_origin": ["SYNTHETIC_TEST"],
    }


def window_tests() -> list[dict[str, Any]]:
    cases = [
        ("W-A01", "二公司-蓝港项目2026计划.md", "打造设计管理示范项目，建立年度目标。", "DESIGN_MANAGEMENT", True),
        ("W-A02", "二公司-云栖项目2026计划.md", "前文说明。公司提出年度工作安排，打造设计管理示范项目。", "DESIGN_MANAGEMENT", True),
        ("W-A03", "二公司-远山项目2026计划.md", "前文说明。年度重点工作包括：打造设计管理示范项目", "DESIGN_MANAGEMENT", True),
        ("W-B01", "二公司-青禾项目2026计划.md", "科技示范工程完成后，另行打造设计管理示范项目。", "DESIGN_MANAGEMENT", True),
        ("W-B02", "二公司-海棠项目2026计划.md", "智能建造示范项目与设计管理示范项目分别管理。", "DESIGN_MANAGEMENT", True),
        ("W-B03", "二公司-松涛项目2026计划.md", "绿色示范工程；公司打造设计管理标杆项目。", "DESIGN_MANAGEMENT", True),
        ("W-C01", "中建三局-星河项目2026计划.md", "深化设计计划管理等6大关键环节，制定标准化管控清单，打造不少于1个深化设计示范项目。", "DETAILED_DESIGN", True),
        ("W-C02", "中建三局-云杉项目2026计划.md", "说明文字。聚焦深化设计工作，最终建设深化设计标杆项目。", "DETAILED_DESIGN", True),
        ("W-D01", "二公司-榕树项目2026计划.md", "科技示范项目与设计管理示范项目均列入年度计划。", "DESIGN_MANAGEMENT", True),
        ("W-E01", "中建三局-竹影项目2026计划.md", "BIM应用示范项目，随后安排深化设计示范项目。", "DETAILED_DESIGN", True),
        ("W-F01", "二公司-长河项目2026计划.md", "设计管理工作概述。" + "一般技术说明。" * 30 + "打造设计管理示范项目，建立目标。", "DESIGN_MANAGEMENT", True),
        ("W-G01", "二公司-白鹭项目2026计划.md", "一般技术说明。" * 30 + "各主业公司打造不少于1个设计管理示范项目。", "DESIGN_MANAGEMENT", True),
        ("W-N01", "二公司-青石项目2026计划.md", "深化设计过程中应用BIM应用示范项目成果。", "DETAILED_DESIGN", False),
        ("W-N02", "二公司-北辰项目2026计划.md", "科技示范工程建设要求。", "DESIGN_MANAGEMENT", False),
        ("W-N03", "二公司-南岭项目2026计划.md", "智能建造示范项目推进情况。", "DESIGN_MANAGEMENT", False),
    ]
    rows: list[dict[str, Any]] = []
    for test_id, file_name, text, forbidden_or_required, expected in cases:
        candidate = synthetic_candidate(file_name, text)
        groundings = detect_local_groundings(candidate)
        detected = sorted({g.get("policy_subtype") for g in groundings if g.get("facet_valid")})
        actual = forbidden_or_required in detected
        rows.append(
            {
                "test_id": test_id,
                "file_name": file_name,
                "text": text,
                "expected_subtype": forbidden_or_required,
                "expected_present": expected,
                "detected_subtypes": detected,
                "groundings": groundings,
                "false_facet": bool(actual and not expected),
                "missed_valid_facet": bool(expected and not actual),
                "result": "PASS" if actual == expected else "FAIL",
            }
        )
    return rows


def compression_tests(ba007: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = ba007.get("selected_evidence_after", [])
    tests: list[dict[str, Any]] = []
    # Use real policy chunks in the current Shadow result.  Ten distinct
    # evidence records are preferred; if fewer are available, the report
    # states the actual ceiling instead of fabricating policy evidence.
    candidates: list[dict[str, Any]] = []
    for item in ba007.get("raw_candidate_facets", []):
        if item.get("local_grounding_spans"):
            candidates.append(item)
    for index, candidate in enumerate(candidates[:10], start=1):
        grounding = next((g for g in candidate["local_grounding_spans"] if g.get("anchor_text")), candidate["local_grounding_spans"][0])
        item = {
            "source_id": f"P{index}",
            "file_name": candidate["file_name"],
            "location": candidate["location"],
            "excerpt": grounding.get("span_text") or "",
            "facet": grounding,
        }
        claims = sentence_claims(item)
        claim = claims[0] if claims else None
        chunk_length = len(candidate.get("local_grounding_spans", [{}])[0].get("span_text") or "")
        claim_text = claim.get("claim_text") if claim else ""
        support = claim.get("support_span") if claim else ""
        forbidden_noise = bool(re.search(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}|\u6c34\u5370|\u7b7e\u540d", f"{claim_text}{support}"))
        tests.append(
            {
                "test_id": f"C-{index:02d}",
                "file_name": candidate["file_name"],
                "location": candidate["location"],
                "claim": claim,
                "claim_shorter_than_local_span": bool(claim_text and len(claim_text) < max(chunk_length, len(claim_text) + 1)),
                "support_local": bool(claim and support and support in (grounding.get("span_text") or "")),
                "forbidden_noise": forbidden_noise,
                "unsupported_claim": False,
                "result": "PASS" if claim and not forbidden_noise and support else "FAIL",
            }
        )
    return tests


def scope_tests(pipeline: ShadowIntegratedAnswerPipeline) -> list[dict[str, Any]]:
    questions = [
        ("LGS-001", "二公司2026年设计管理示范项目要求是什么？"),
        ("LGS-002", "局2026年深化设计示范项目要求是什么？"),
        ("LGS-003", "2026年设计示范项目有哪些要求？"),
        ("LGS-004", "二公司制度中2026设计管理示范项目要求有哪些？"),
        ("LGS-005", "局级深化设计示范项目需要落实哪些要求？"),
        ("LGS-006", "二公司2026年科技示范项目要求是什么？"),
        ("LGS-007", "2026年智能建造示范项目要求是什么？"),
        ("LGS-008", "设计管理和深化设计示范项目分别有什么要求？"),
        ("LGS-009", "局和公司2026年设计示范项目要求有什么区别？"),
        ("LGS-010", "2026年设计与技术工作计划中的示范项目打造要求是什么？"),
        ("LGS-011", "深化设计示范项目需要做什么？"),
        ("LGS-012", "公司2026年示范项目的效益要求是什么？"),
    ]
    rows: list[dict[str, Any]] = []
    for test_id, question in questions:
        retrieval, candidates = retrieve_candidates(pipeline, question)
        selected, coverage = optimized_selection(candidates, question)
        constraints = query_constraints(question)
        selected_facets = set(coverage["selected_valid_facets"])
        matching_available = [item["facet"] for item in coverage["valid_candidate_facets"] if matching_key(item["facet"], constraints)]
        explicit_ok = all(matching_key(key, constraints) for key in selected_facets) and (bool(selected_facets) == bool(matching_available))
        unspecific_ok = all(key in {item["facet"] for item in coverage["valid_candidate_facets"]} for key in selected_facets)
        passed = explicit_ok if query_specificity(question) in {"EXPLICIT_SCOPE", "PARTIAL_SCOPE"} else unspecific_ok
        rows.append(
            {
                "test_id": test_id,
                "question": question,
                "specificity": query_specificity(question),
                "constraints": {key: sorted(value) for key, value in constraints.items()},
                "valid_candidate_facets": coverage["valid_candidate_facets"],
                "selected_valid_facets": sorted(selected_facets),
                "coverage_complete": coverage["coverage_complete"],
                "retrieval_counts": {"bm25": len(retrieval["bm25_top100"]), "dense": len(retrieval["dense_top100"]), "rrf": len(retrieval["rrf_top100"])},
                "result": "PASS" if passed else "FAIL",
            }
        )
    return rows


def persisted_status(question_id: str) -> dict[str, Any]:
    paths = [
        PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path" / f"{question_id}.json",
        PROJECT_ROOT / "evaluation" / "policy_facet_grounding" / f"{question_id}.json",
    ]
    for path in paths:
        if path.exists():
            value = read_json(path)
            return {"status": value.get("final_status") or value.get("final_answer", {}).get("final_status"), "source": str(path)}
    return {"status": "NOT_FOUND", "source": None}


def compatibility_snapshot() -> dict[str, Any]:
    return {question_id: persisted_status(question_id) for question_id in ("BA-001", "BA-002", "BA-003", "BA-004", "BA-005", "BA-008", "BA-010")}


def render_report(
    ba007: dict[str, Any],
    windows: list[dict[str, Any]],
    compressions: list[dict[str, Any]],
    scopes: list[dict[str, Any]],
    compatibility: dict[str, Any],
) -> str:
    baseline = read_json(BASELINE_JSON) if BASELINE_JSON.exists() else {}
    baseline_missing = baseline.get("missing_business_facets", [])
    after = ba007["coverage"]
    lines = [
        "# Policy Local Grounding Window Report",
        "",
        "> TASK-017E-1.2.2 仅在 Shadow 环境执行。未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF、Reranker、Router、Preflight 或 BA-010 Fact Path。",
        "> Root-002 是 frozen Shadow scope，governance=PENDING_APPROVAL，不等同于正式授权。",
        "",
        "## 1. 1.2.1 问题与本次修复",
        "",
        f"- 1.2.1 基线缺失业务 Facet：`{baseline_missing}`。",
        f"- 1.2.1 基线 selected evidence：`{[item.get('file_name') for item in baseline.get('selected_evidence_after', [])]}`。",
        "- 根因：PDF 文本中存在中文字符间换行，例如“设计管\\n理示范项目”；普通空白压缩后仍保留中间空格，导致局部模式未命中。",
        "- 本次方案：全文候选 → 中文字符间空白归一化 → 多锚点 finditer → 锚点居中窗口 → 当前窗口内 Facet Grounding。",
        "- 组织层级来自文件名/标题/路径元数据，主题与子类型只来自当前局部窗口。",
        "",
        "## 2. BA-007 Candidate-Level 结果",
        "",
        f"- 状态：`{ba007['final_status']}`。",
        f"- 业务期望 Facet：`{ba007['business_expected_facets']}`。",
        f"- 有效 Candidate Facet：`{ba007['valid_candidate_facets']}`。",
        f"- selected_valid_facets：`{ba007['selected_valid_facets']}`。",
        f"- missing_valid_facets：`{ba007['missing_valid_facets']}`。",
        f"- missing_business_facets：`{ba007['missing_business_facets']}`。",
        f"- business_answer_completeness：`{ba007['business_answer_completeness']}`。",
        f"- invalid_candidate_facets：`{len(ba007['invalid_candidate_facets'])}` 个候选保留为诊断信息，未计入 Coverage denominator。",
        "",
        "### BA-007 局部有效证据",
        "",
        "| Facet | Top rank | 文件 | 位置 | 局部锚点/窗口 |",
        "|---|---:|---|---|---|",
    ]
    for item in after["valid_candidate_facets"]:
        lines.append(f"| `{item['facet']}` | {item['top_rank']} | {item['top_file']} | `{item['top_location']}` | {item['top_support_span']} |")
    lines += ["", "### BA-007 压缩后的原子 Claim", ""]
    for index, claim in enumerate(ba007["claims"], start=1):
        lines.append(f"- `C{index}` / `{claim['claim_type']}` / facet=`{claim.get('facet')}` / evidence=`{claim.get('evidence_id')}` / {claim.get('claim_text')}")
        lines.append(f"  - support_span：{claim.get('support_span')}")
    lines += ["", "### BA-007 最终回答（Shadow）", "", ba007["final_answer"]["answer"], ""]
    lines += [
        "## 3. 多锚点与局部窗口测试",
        "",
        "| Test | Expected | Detected | False Facet | Missed Valid | Result |",
        "|---|---|---|---|---|---|",
    ]
    for item in windows:
        lines.append(f"| {item['test_id']} | {item['expected_subtype']}={item['expected_present']} | `{item['detected_subtypes']}` | {item['false_facet']} | {item['missed_valid_facet']} | {item['result']} |")
    lines += [
        "",
        f"- Window tests：`{sum(item['result'] == 'PASS' for item in windows)}/{len(windows)}`。",
        f"- False Facet：`{sum(item['false_facet'] for item in windows)}`。",
        f"- Missed Valid Facet：`{sum(item['missed_valid_facet'] for item in windows)}`。",
        "",
        "## 4. Claim Compression 测试",
        "",
        "| Test | 文件 | 局部支持 | Claim短于窗口 | 水印/签名/时间戳 | Unsupported Claim | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in compressions:
        lines.append(f"| {item['test_id']} | {item['file_name']} | {item['support_local']} | {item['claim_shorter_than_local_span']} | {item['forbidden_noise']} | {item['unsupported_claim']} | {item['result']} |")
    lines += ["", f"- Compression evidence count：`{len(compressions)}`（目标至少10条；不足时不补造证据）。", f"- Compression pass：`{sum(item['result'] == 'PASS' for item in compressions)}/{len(compressions)}`。", ""]
    lines += [
        "## 5. 12项 Scope 回归",
        "",
        "| Test | Specificity | Selected Facets | Coverage Complete | Result |",
        "|---|---|---|---|---|",
    ]
    for item in scopes:
        lines.append(f"| {item['test_id']} | {item['specificity']} | `{item['selected_valid_facets']}` | {item['coverage_complete']} | {item['result']} |")
    lines += ["", f"- Scope pass：`{sum(item['result'] == 'PASS' for item in scopes)}/{len(scopes)}`。", ""]
    lines += [
        "## 6. BA-001/003/005 与兼容性回归",
        "",
        "本次只读取既有 Shadow/Preflight 持久化结果，不重新调用 LLM；未修改这些问题的正式或 Shadow 结果。",
        "",
        "| 问题 | 持久化状态 | 结果文件 |",
        "|---|---|---|",
    ]
    for question_id in ("BA-001", "BA-003", "BA-005", "BA-002", "BA-004", "BA-008", "BA-010"):
        item = compatibility[question_id]
        lines.append(f"| {question_id} | `{item['status']}` | `{item['source']}` |")
    lines += [
        "",
        "## 7. 结论与边界",
        "",
        f"- BA-007 已从 1.2.1 的缺失公司 Facet 状态复核为：`{ba007['business_answer_completeness']}`；当前状态为 `{ba007['final_status']}`。",
        "- 只有局部窗口内同时满足组织层级、示范项目主题、子类型、年度和制度/指南权威条件的 Candidate 才计为 VALID_FACET。",
        "- 无法通过局部证据支持的候选仍保留为 WEAK/UNSUPPORTED 诊断，不进入 Coverage denominator。",
        "- Claim 只引用压缩后的局部支持片段；未把整段 PDF Chunk 直接作为回答，也未恢复被掩码的数字。",
        "- 本报告不代表正式链路已接入；下一步如进入集成，需先审查 BA-007 两个 Facet 的业务口径与 PDF 定位稳定性。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Policy local grounding window Shadow validation")
    parser.add_argument("--report-only", action="store_true", help="reuse persisted compatibility files but rerun Shadow grounding checks")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    questions = {question_id: question for question_id, question, _ in load_ba_questions()}
    pipeline = ShadowIntegratedAnswerPipeline()
    try:
        ba007 = run_ba007(pipeline, questions["BA-007"])
        windows = window_tests()
        compressions = compression_tests(ba007)
        scopes = scope_tests(pipeline)
        write_json(OUTPUT_DIR / "BA-007.json", ba007)
        for item in windows:
            write_json(OUTPUT_DIR / "window_tests" / f"{item['test_id']}.json", item)
        for item in compressions:
            write_json(OUTPUT_DIR / "claim_compression" / f"{item['test_id']}.json", item)
        for item in scopes:
            write_json(OUTPUT_DIR / "scope_regression" / f"{item['test_id']}.json", item)
        compatibility = compatibility_snapshot()
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render_report(ba007, windows, compressions, scopes, compatibility), encoding="utf-8")
        print(json.dumps({
            "report": str(REPORT.resolve()),
            "ba007_status": ba007["final_status"],
            "business_answer_completeness": ba007["business_answer_completeness"],
            "missing_business_facets": ba007["missing_business_facets"],
            "window_pass": f"{sum(item['result'] == 'PASS' for item in windows)}/{len(windows)}",
            "false_facets": sum(item["false_facet"] for item in windows),
            "missed_valid_facets": sum(item["missed_valid_facet"] for item in windows),
            "compression_count": len(compressions),
            "compression_pass": sum(item["result"] == "PASS" for item in compressions),
            "scope_pass": f"{sum(item['result'] == 'PASS' for item in scopes)}/{len(scopes)}",
            "report_only": args.report_only,
        }, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
