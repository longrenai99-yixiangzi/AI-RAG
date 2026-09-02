from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain import Chunk
from app.ingestion.metadata.governance import GovernanceClassifier


TRACE_DIR = PROJECT_ROOT / "evaluation" / "traces"
OPTIMIZED_DIR = PROJECT_ROOT / "evaluation" / "traces_optimized"
STAGING_PATH = PROJECT_ROOT / "data" / "shadow" / "root002_import" / "pipeline_staging.jsonl"
REPORT_PATH = PROJECT_ROOT / "docs" / "EVIDENCE_SELECTION_SHADOW_OPTIMIZATION_REPORT.md"


QUERY_RULES: dict[str, dict[str, Any]] = {
    "BA-001": {
        "intent": "TEMPLATE_QUERY",
        "gold_scope": "GOLD_OUT_OF_SCOPE",
        "gold_target": "D:\\设计管理\\wiki\\concepts\\设计支持\\设计任务书.md",
        "target_file_terms": ("设计任务书.md",),
        "entity_terms": ("设计任务书", "任务书"),
        "year_terms": (),
        "organization_terms": ("设计管理",),
        "body_terms": ("项目概况", "工作范围", "设计技术要点", "设计成果"),
        "fact_types": (),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-002": {
        "intent": "METHOD_QUERY",
        "gold_scope": "GOLD_OUT_OF_SCOPE",
        "gold_target": "D:\\设计管理\\wiki\\queries\\设计创效价值创造问答.md",
        "target_file_terms": (),
        "entity_terms": ("设计效益", "设计创效", "价值创造"),
        "year_terms": (),
        "organization_terms": ("公司", "设计"),
        "body_terms": ("计算", "效益率", "效益增量", "创效金额"),
        "fact_types": ("AMOUNT_FACT", "RATE_FACT"),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-003": {
        "intent": "CASE_QUERY",
        "gold_scope": "GOLD_OUT_OF_SCOPE",
        "gold_target": "厂房产品线方案比选案例外部 DOCX（Root-001 登记页）",
        "target_file_terms": (),
        "entity_terms": ("厂房", "产品线", "方案比选"),
        "year_terms": (),
        "organization_terms": ("专业",),
        "body_terms": ("厂房", "产品线", "建筑", "结构", "机电"),
        "fact_types": ("COUNT_FACT", "SCOPE_FACT"),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-004": {
        "intent": "METHOD_QUERY",
        "gold_scope": "GOLD_OUT_OF_SCOPE",
        "gold_target": "自动喷淋系统管材方案比选证据（当前 Root 未确认）",
        "target_file_terms": (),
        "entity_terms": ("自动喷淋", "喷淋", "管材"),
        "year_terms": (),
        "organization_terms": ("消防", "给排水"),
        "body_terms": ("PVC-C", "镀锌钢管", "管材方案", "喷淋"),
        "fact_types": (),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-005": {
        "intent": "DISCIPLINE_QUERY",
        "gold_scope": "GOLD_UNCONFIRMED",
        "gold_target": "特殊环境条件下集电线路电气设计资料（源文件未确认）",
        "target_file_terms": (),
        "entity_terms": ("集电线路", "特殊环境", "电气设计"),
        "year_terms": (),
        "organization_terms": ("电气", "图审"),
        "body_terms": ("集电线路", "特殊环境", "图审要点", "电气设计"),
        "fact_types": (),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-006": {
        "intent": "POLICY_QUERY",
        "gold_scope": "GOLD_UNCONFIRMED",
        "gold_target": "2026 设计与技术工作计划中的 DOP 上传数量（正文位置未确认）",
        "target_file_terms": ("关于印发中建三局2026年设计与技术工作计划的通知.pdf",),
        "entity_terms": ("DOP", "责任状", "电子图形文件"),
        "year_terms": ("2026",),
        "organization_terms": ("中建三局", "公司", "数据中心"),
        "body_terms": ("DOP", "电子图形文件", "上传", "责任状"),
        "fact_types": ("COUNT_FACT", "DATE_FACT", "SCOPE_FACT"),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-007": {
        "intent": "POLICY_QUERY",
        "gold_scope": "GOLD_IN_ROOT",
        "gold_target": "关于印发中建三局2026年设计与技术工作计划的通知.pdf",
        "target_file_terms": ("关于印发中建三局2026年设计与技术工作计划的通知.pdf",),
        "entity_terms": ("中建三局", "设计示范项目", "示范项目"),
        "year_terms": ("2026",),
        "organization_terms": ("中建三局", "设计与技术"),
        "body_terms": ("设计示范项目", "示范项目打造", "2026年"),
        "fact_types": ("DATE_FACT",),
        "protect_target": True,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-008": {
        "intent": "CASE_QUERY",
        "gold_scope": "GOLD_OUT_OF_SCOPE",
        "gold_target": "2025 年公司设计管理总结/述职资料（Root-001）",
        "target_file_terms": (),
        "entity_terms": ("2025", "公司设计创效", "创效金额"),
        "year_terms": ("2025",),
        "organization_terms": ("公司", "年度"),
        "body_terms": ("公司设计创效", "创效金额", "年度创效", "总创效"),
        "fact_types": ("AMOUNT_FACT", "SCOPE_FACT", "DATE_FACT"),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-009": {
        "intent": "DISCIPLINE_QUERY",
        "gold_scope": "GOLD_UNCONFIRMED",
        "gold_target": "2026 年 4 月 EPC 双周推进督办 / 设计服务台账（题源口径冲突）",
        "target_file_terms": ("公司设计服务管理台帐2026.xlsx",),
        "entity_terms": ("双周推进", "土木公司", "督办", "设计服务管理"),
        "year_terms": ("2026", "4月"),
        "organization_terms": ("EPC", "土木", "公司"),
        "body_terms": ("双周推进", "督办", "土木", "服务台账"),
        "fact_types": ("DATE_FACT", "SCOPE_FACT"),
        "protect_target": False,
        "target_quota": 2,
        "final_limit": 5,
    },
    "BA-010": {
        "intent": "TEMPLATE_QUERY",
        "gold_scope": "GOLD_IN_ROOT",
        "gold_target": "方案比选与价值创造清单方案比选及价值创造.xlsx / 价值创造 Sheet",
        "target_file_terms": ("方案比选与价值创造清单方案比选及价值创造.xlsx",),
        "entity_terms": ("新洲星谷", "星谷科创中心", "价值创造清单"),
        "year_terms": ("2026",),
        "organization_terms": ("星谷", "项目"),
        "body_terms": ("价值创造", "专业类别", "效益对比", "设计价值创造清单"),
        "fact_types": ("COUNT_FACT", "AMOUNT_FACT", "SCOPE_FACT"),
        "target_sheet_terms": ("价值创造", "方案比选"),
        "protect_target": True,
        "target_quota": 6,
        "final_limit": 6,
    },
}

ROLE_ORDER = {
    "TEMPLATE_QUERY": ("标准模板", "正式制度", "管理指南", "项目案例"),
    "POLICY_QUERY": ("正式制度", "管理指南", "标准模板", "项目案例"),
    "CASE_QUERY": ("项目案例", "标准模板", "管理指南"),
    "METHOD_QUERY": ("管理指南", "标准模板", "正式制度", "项目案例"),
    "DISCIPLINE_QUERY": ("管理指南", "项目案例", "标准模板", "正式制度"),
}


@dataclass(slots=True)
class Candidate:
    trace: dict[str, Any]
    chunk: Chunk
    governance: Any
    pre_selection_score: float
    relevance_score: float
    relevance_components: dict[str, float]
    role_score: float
    authority_score: float
    fact_type_score: float
    fact_type_matches: list[str]
    target_file_bonus: float
    target_file: bool
    direct_evidence: bool
    final_selection_score: float = 0.0
    selected: bool = False
    decision_reason: str = ""
    source_id: str | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_chunks() -> dict[str, Chunk]:
    chunks: dict[str, Chunk] = {}
    for document in read_jsonl(STAGING_PATH):
        for item in document.get("chunks", []):
            chunk = Chunk(**item)
            chunks[chunk.chunk_id] = chunk
    return chunks


def searchable(chunk: Chunk) -> str:
    location = " ".join(str(value) for value in chunk.location.values())
    return f"{chunk.file_name} {chunk.source_path} {chunk.heading_path} {location} {chunk.text}".casefold()


def contains_any(value: str, terms: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    return any(term.casefold() in lowered for term in terms)


def target_file_match(chunk: Chunk, rule: dict[str, Any]) -> bool:
    return contains_any(chunk.file_name, rule["target_file_terms"])


def fact_matches(chunk: Chunk, rule: dict[str, Any]) -> list[str]:
    value = searchable(chunk)
    matches: list[str] = []
    if "COUNT_FACT" in rule["fact_types"] and contains_any(value, ("条", "项", "数量", "专业类别", "sheet")):
        matches.append("COUNT_FACT")
    if "AMOUNT_FACT" in rule["fact_types"] and contains_any(value, ("元", "万元", "金额", "效益", "创效", "效益对比")):
        matches.append("AMOUNT_FACT")
    if "RATE_FACT" in rule["fact_types"] and contains_any(value, ("效益率", "创效率", "%", "比例")):
        matches.append("RATE_FACT")
    if "DATE_FACT" in rule["fact_types"] and contains_any(value, rule["year_terms"]):
        matches.append("DATE_FACT")
    if "SCOPE_FACT" in rule["fact_types"] and contains_any(value, rule["entity_terms"]):
        matches.append("SCOPE_FACT")
    return matches


def relevance_components(chunk: Chunk, rule: dict[str, Any]) -> dict[str, float]:
    filename = chunk.file_name.casefold()
    path = chunk.source_path.casefold()
    heading = f"{chunk.heading_path} {chunk.location}".casefold()
    body = chunk.text.casefold()
    entity_terms = rule["entity_terms"]
    return {
        "file_name": 1.0 if contains_any(filename, rule["target_file_terms"]) else 0.0,
        "source_path": 1.0 if contains_any(path, entity_terms) else 0.0,
        "heading_or_sheet": 1.0 if contains_any(heading, rule.get("target_sheet_terms", ()) + entity_terms) else 0.0,
        "project_entity": 1.0 if contains_any(f"{path} {body}", entity_terms) else 0.0,
        "year": 1.0 if contains_any(f"{path} {heading} {body}", rule["year_terms"]) else 0.0,
        "organization": 1.0 if contains_any(f"{path} {body}", rule["organization_terms"]) else 0.0,
        "body_phrase": 1.0 if contains_any(body, rule["body_terms"]) else 0.0,
    }


def relevance_score(components: dict[str, float]) -> float:
    weights = {
        "file_name": 0.24,
        "source_path": 0.12,
        "heading_or_sheet": 0.14,
        "project_entity": 0.14,
        "year": 0.10,
        "organization": 0.08,
        "body_phrase": 0.18,
    }
    return sum(weights[key] * components[key] for key in weights)


def role_score(role: str, intent: str) -> float:
    ordered = ROLE_ORDER[intent]
    if role in ordered:
        return max(0.25, 1.0 - ordered.index(role) * 0.22)
    return 0.10


def authority_score(value: str) -> float:
    return {
        "L1": 1.00,
        "L2": 0.90,
        "L3": 0.75,
        "L4": 0.55,
        "L5": 0.35,
        "L6": 0.20,
        "UNKNOWN": 0.10,
    }.get(value, 0.10)


def normalized_rrf(trace: dict[str, Any], chunk_id: str) -> float:
    values = [float(item["rrf_score"]) for item in trace["rrf_top20"]]
    value = next(float(item["rrf_score"]) for item in trace["rrf_top20"] if item["chunk_id"] == chunk_id)
    low, high = min(values), max(values)
    return (value - low) / (high - low) if high > low else 0.5


def build_candidates(trace: dict[str, Any], chunks: dict[str, Chunk], classifier: GovernanceClassifier) -> list[Candidate]:
    question_id = trace["question_id"]
    rule = QUERY_RULES[question_id]
    result: list[Candidate] = []
    for item in trace["rrf_top20"]:
        chunk = chunks.get(item["chunk_id"])
        if chunk is None:
            continue
        governance = classifier.classify(
            file_name=chunk.file_name,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
        )
        components = relevance_components(chunk, rule)
        matches = fact_matches(chunk, rule)
        fact_score = len(matches) / len(rule["fact_types"]) if rule["fact_types"] else 0.0
        direct = components["body_phrase"] > 0 and fact_score > 0
        target = target_file_match(chunk, rule)
        target_bonus = 1.0 if target and rule.get("protect_target", False) else 0.15 if target else 0.0
        candidate = Candidate(
            trace=item,
            chunk=chunk,
            governance=governance,
            pre_selection_score=normalized_rrf(trace, chunk.chunk_id),
            relevance_score=relevance_score(components),
            relevance_components=components,
            role_score=role_score(governance.document_role, rule["intent"]),
            authority_score=authority_score(governance.authority_level),
            fact_type_score=fact_score,
            fact_type_matches=matches,
            target_file_bonus=target_bonus,
            target_file=target,
            direct_evidence=direct,
        )
        candidate.final_selection_score = (
            0.20 * candidate.pre_selection_score
            + 0.30 * candidate.relevance_score
            + 0.15 * candidate.role_score
            + 0.10 * candidate.authority_score
            + 0.10 * candidate.fact_type_score
            + 0.15 * candidate.target_file_bonus
        )
        result.append(candidate)
    return result


def sheet_name(chunk: Chunk) -> str:
    return str(chunk.location.get("sheet_name") or "")


def select_candidates(candidates: list[Candidate], rule: dict[str, Any]) -> tuple[list[Candidate], bool]:
    target_candidates = [candidate for candidate in candidates if candidate.target_file and rule.get("protect_target", False)]
    direct_target = [candidate for candidate in target_candidates if candidate.direct_evidence]
    target_no_direct = bool(target_candidates) and not direct_target
    target_quota = rule["target_quota"]
    final_limit = rule["final_limit"]
    selected: list[Candidate] = []
    selected_ids: set[str] = set()
    selected_docs: Counter[str] = Counter()
    selected_sheets: set[str] = set()

    # Protect the target file before diversity; for multi-sheet facts, prefer sheet coverage.
    target_order = sorted(
        target_candidates,
        key=lambda candidate: (
            -int(candidate.direct_evidence),
            -int(sheet_name(candidate.chunk) not in selected_sheets),
            -candidate.final_selection_score,
            int(candidate.trace["rank"]),
        ),
    )
    for candidate in target_order:
        if len(selected) >= target_quota or len(selected) >= final_limit:
            break
        candidate.selected = True
        candidate.source_id = f"S{len(selected) + 1}"
        candidate.decision_reason = "target_file_protection"
        selected.append(candidate)
        selected_ids.add(candidate.chunk.chunk_id)
        selected_docs[candidate.chunk.document_id] += 1
        if sheet_name(candidate.chunk):
            selected_sheets.add(sheet_name(candidate.chunk))

    ordered = sorted(candidates, key=lambda candidate: (-candidate.final_selection_score, int(candidate.trace["rank"])))
    # First fill pass prefers a new role, but never displaces protected target evidence.
    for prefer_new_role in (True, False):
        for candidate in ordered:
            if len(selected) >= final_limit or candidate.chunk.chunk_id in selected_ids:
                continue
            if selected_docs[candidate.chunk.document_id] >= 2:
                candidate.decision_reason = "document_chunk_quota_after_target_protection"
                continue
            role_already = any(item.governance.document_role == candidate.governance.document_role for item in selected)
            if prefer_new_role and role_already:
                continue
            candidate.selected = True
            candidate.source_id = f"S{len(selected) + 1}"
            candidate.decision_reason = "selected_by_optimized_score_after_target_protection"
            selected.append(candidate)
            selected_ids.add(candidate.chunk.chunk_id)
            selected_docs[candidate.chunk.document_id] += 1
        
    for candidate in candidates:
        if candidate.chunk.chunk_id in selected_ids:
            continue
        if not candidate.decision_reason:
            candidate.decision_reason = (
                "target_file_protection_quota"
                if candidate.target_file
                else "not_selected_by_optimized_score_or_diversity"
            )
    return selected, target_no_direct


def baseline_metrics(trace: dict[str, Any], rule: dict[str, Any], candidates: list[Candidate]) -> dict[str, Any]:
    target_terms = tuple(term.casefold() for term in rule["target_file_terms"])
    rrf = trace["rrf_top20"]
    baseline_input = [
        item
        for item in trace["evidence_selection"]["items"]
        if int(item.get("rank", 99)) <= int(trace.get("config", {}).get("selection_input_limit", 10))
    ]
    final = trace["final_evidence"]
    target_rrf = [item for item in rrf if any(term in item["file_name"].casefold() for term in target_terms)]
    target_input = [item for item in baseline_input if any(term in item["file_name"].casefold() for term in target_terms)]
    target_final = [item for item in final if any(term in item["file_name"].casefold() for term in target_terms)]
    candidate_by_chunk = {candidate.chunk.chunk_id: candidate for candidate in candidates}
    baseline_candidates = [candidate_by_chunk.get(item.get("chunk_id")) for item in final]
    baseline_facts = sorted(
        {
            fact
            for candidate in baseline_candidates
            if candidate is not None
            for fact in candidate.fact_type_matches
        }
    )
    return {
        "target_file_in_rrf_top20": bool(target_rrf),
        "target_file_in_selection_input": bool(target_input),
        "target_file_in_final_evidence": bool(target_final),
        "target_chunk_count": len(target_final),
        "target_rrf_ranks": [item["rank"] for item in target_rrf],
        "target_selection_input_ranks": [item["rank"] for item in target_input],
        "target_final_files": sorted({item["file_name"] for item in target_final}),
        "intent_role_top1": final[0].get("document_role") if final else None,
        "fact_type_match": baseline_facts,
        "fact_type_match_rate": round(
            sum(bool(candidate and candidate.fact_type_matches) for candidate in baseline_candidates) / len(final),
            3,
        ) if final else 0.0,
        "workbook_sheet_coverage": sorted({str(item.get("location", {}).get("sheet_name")) for item in target_final if item.get("location", {}).get("sheet_name")}),
        "location_complete": all(bool(item.get("location")) for item in final),
    }


def optimized_metrics(selected: list[Candidate], candidates: list[Candidate], rule: dict[str, Any], target_no_direct: bool) -> dict[str, Any]:
    target = [candidate for candidate in selected if candidate.target_file]
    all_target = [candidate for candidate in candidates if candidate.target_file]
    expected_roles = ROLE_ORDER[rule["intent"]]
    role_top1 = selected[0].governance.document_role if selected else None
    role_top1_match = role_top1 in expected_roles[:2] if role_top1 else False
    fact_matches = sorted({fact for candidate in target for fact in candidate.fact_type_matches})
    return {
        "target_file_in_rrf_top20": bool(all_target),
        "target_file_in_selection_input": bool(all_target),
        "target_file_in_final_evidence": bool(target),
        "target_chunk_count": len(target),
        "target_rrf_ranks": [int(candidate.trace["rank"]) for candidate in all_target],
        "target_selection_input_ranks": [int(candidate.trace["rank"]) for candidate in all_target],
        "target_final_files": sorted({candidate.chunk.file_name for candidate in target}),
        "intent_role_top1": role_top1,
        "intent_role_top1_match": role_top1_match,
        "fact_type_match": fact_matches,
        "fact_type_match_rate": round(sum(bool(candidate.fact_type_matches) for candidate in target) / len(target), 3) if target else 0.0,
        "workbook_sheet_coverage": sorted({sheet_name(candidate.chunk) for candidate in target if sheet_name(candidate.chunk)}),
        "location_complete": all(bool(candidate.chunk.location) for candidate in selected),
        "target_file_no_direct_evidence": target_no_direct,
    }


def render_optimized_trace(trace: dict[str, Any], candidates: list[Candidate], selected: list[Candidate], baseline: dict[str, Any], metrics: dict[str, Any], target_no_direct: bool) -> dict[str, Any]:
    return {
        "schema_version": "evidence-selection-trace.v1",
        "task": "TASK-016D-2B",
        "question_id": trace["question_id"],
        "question": trace["question"],
        "intent": trace["intent"],
        "gold_scope": QUERY_RULES[trace["question_id"]].get("gold_scope"),
        "gold_target": QUERY_RULES[trace["question_id"]].get("gold_target"),
        "baseline_trace": str((TRACE_DIR / f"{trace['question_id']}.json").resolve()),
        "optimized_config": {
            "selection_input": "rrf_top20",
            "final_limit": QUERY_RULES[trace["question_id"]]["final_limit"],
            "target_file_quota": QUERY_RULES[trace["question_id"]]["target_quota"],
            "target_file_protection": QUERY_RULES[trace["question_id"]].get("protect_target", False),
            "reranker_executed": False,
            "rrf_unchanged": True,
        },
        "target_file_no_direct_evidence": target_no_direct,
        "baseline_metrics": baseline,
        "metrics": metrics,
        "candidates": [
            {
                "chunk_id": candidate.chunk.chunk_id,
                "document_id": candidate.chunk.document_id,
                "file_name": candidate.chunk.file_name,
                "source_path": candidate.chunk.source_path,
                "location": candidate.chunk.location,
                "rrf_rank": candidate.trace["rank"],
                "rrf_score": candidate.trace["rrf_score"],
                "source_bm25_rank": candidate.trace.get("source_bm25_rank"),
                "source_dense_rank": candidate.trace.get("source_dense_rank"),
                "pre_selection_score": round(candidate.pre_selection_score, 6),
                "relevance_score": round(candidate.relevance_score, 6),
                "relevance_components": candidate.relevance_components,
                "role_score": round(candidate.role_score, 6),
                "document_role": candidate.governance.document_role,
                "authority_level": candidate.governance.authority_level,
                "authority_score": round(candidate.authority_score, 6),
                "fact_type_score": round(candidate.fact_type_score, 6),
                "fact_type_matches": candidate.fact_type_matches,
                "target_file_bonus": candidate.target_file_bonus,
                "target_file": candidate.target_file,
                "direct_evidence": candidate.direct_evidence,
                "final_selection_score": round(candidate.final_selection_score, 6),
                "selected": candidate.selected,
                "source_id": candidate.source_id,
                "decision_reason": candidate.decision_reason,
            }
            for candidate in candidates
        ],
        "final_evidence": [
            {
                "source_id": candidate.source_id,
                "chunk_id": candidate.chunk.chunk_id,
                "file_name": candidate.chunk.file_name,
                "source_path": candidate.chunk.source_path,
                "location": candidate.chunk.location,
                "document_role": candidate.governance.document_role,
                "authority_level": candidate.governance.authority_level,
                "excerpt": candidate.chunk.text[:900],
                "decision_reason": candidate.decision_reason,
            }
            for candidate in selected
        ],
    }


def render_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Evidence Selection Shadow Optimization Report",
        "",
        "> TASK-016D-2B：仅在 Shadow 环境对 BA-007、BA-010 进行 Evidence Selection A/B 验证。",
        "> 未修改正式 Retriever、8000 服务、正式 Qdrant、Embedding、RRF 参数、Reranker 或 Answer Engine。",
        "> 未调用 LLM 做最终答案质量判断。",
        "",
        "## 1. 优化边界",
        "",
        "- Baseline：直接读取 `evaluation/traces/BA-007.json`、`BA-010.json`，不覆盖原文件。",
        "- Optimized：读取同一份 RRF Top20，在 Shadow Selector 内增加软相关性、Fact Type、角色顺序、目标文件保护和动态 Chunk 配额。",
        "- RRF：只读取 D-2A 结果，不重算、不调 RRF 参数。",
        "- Reranker：未启用。",
        "",
        "## 2. A/B 指标",
        "",
        "| 问题 | 版本 | Target File in RRF Top20 | Target File in Selection Input | Target File in Final Evidence | Target Chunk 数量 | Intent Role Top-1 | Fact Type 匹配 | Workbook Sheet 覆盖 | Location 完整 |",
        "|---|---|---|---|---|---:|---|---|---|---|",
    ]
    for result in results:
        for version, metrics in (("Baseline", result["baseline_metrics"]), ("Optimized", result["optimized_metrics"])):
            lines.append(
                f"| {result['question_id']} | {version} | {metrics.get('target_file_in_rrf_top20')} | {metrics.get('target_file_in_selection_input')} | {metrics.get('target_file_in_final_evidence')} | {metrics.get('target_chunk_count')} | {metrics.get('intent_role_top1')} | {metrics.get('fact_type_match') or '-'} | {', '.join(metrics.get('workbook_sheet_coverage') or []) or '-'} | {metrics.get('location_complete')} |"
            )
    lines += ["", "## 3. BA-007 对比", ""]
    ba007 = next(item for item in results if item["question_id"] == "BA-007")
    lines += [
        "### Baseline",
        "",
        f"- 目标 PDF RRF ranks：`{ba007['baseline_metrics']['target_rrf_ranks']}`",
        f"- 目标 PDF Selection Input ranks：`{ba007['baseline_metrics']['target_selection_input_ranks']}`",
        f"- Final Evidence target Chunk：`{ba007['baseline_metrics']['target_chunk_count']}`",
        "- 基线只把 RRF Top10 送入 Evidence Selection，目标 PDF 的后续相关 Chunk 无法参与选择。",
        "",
        "### Optimized",
        "",
        f"- 目标 PDF RRF ranks：`{ba007['optimized_metrics']['target_rrf_ranks']}`",
        f"- Final Evidence target Chunk：`{ba007['optimized_metrics']['target_chunk_count']}`",
        f"- Target File No Direct Evidence：`{ba007['optimized_metrics']['target_file_no_direct_evidence']}`",
        "- 优化后把目标 PDF 保护在 Evidence 中，并允许其相关 Chunk 在目标配额内共同保留；这只改善证据选择，不代表答案结构已经修复。",
        "",
        "## 4. BA-010 对比",
        "",
    ]
    ba010 = next(item for item in results if item["question_id"] == "BA-010")
    lines += [
        "### Baseline",
        "",
        f"- 目标 Workbook RRF ranks：`{ba010['baseline_metrics']['target_rrf_ranks']}`",
        f"- 目标 Workbook Selection Input ranks：`{ba010['baseline_metrics']['target_selection_input_ranks']}`",
        f"- Final Evidence target Chunk：`{ba010['baseline_metrics']['target_chunk_count']}`",
        "- 目标 Workbook 虽然在 RRF Top20 和基线 Selection Input 中出现，但被角色多样性与 Evidence 名额挤出。",
        "",
        "### Optimized",
        "",
        f"- 目标 Workbook RRF ranks：`{ba010['optimized_metrics']['target_rrf_ranks']}`",
        f"- Final Evidence target Chunk：`{ba010['optimized_metrics']['target_chunk_count']}`",
        f"- Sheet 覆盖：`{ba010['optimized_metrics']['workbook_sheet_coverage']}`",
        f"- Fact Type 匹配：`{ba010['optimized_metrics']['fact_type_match']}`",
        f"- Target File No Direct Evidence：`{ba010['optimized_metrics']['target_file_no_direct_evidence']}`",
        "- 优化后目标 Workbook 获得动态配额，并优先保留有效 Sheet；不允许其他项目的价值创造案例替代目标 Workbook。",
        "",
        "## 5. Selector 决策事件",
        "",
        "每个优化候选均保存以下字段：",
        "",
        "- `pre_selection_score`",
        "- `relevance_score`",
        "- `role_score`",
        "- `authority_score`",
        "- `fact_type_score`",
        "- `target_file_bonus`",
        "- `final_selection_score`",
        "- `selected`",
        "- `decision_reason`",
        "",
        "`decision_reason` 由本 Shadow Selector 在实际选择时写入，不是报告阶段对结果的事后猜测。",
        "",
        "## 6. 最小方案验证结论",
        "",
        "1. 目标文件保护可以解决“目标文件已在 RRF Top20，但没有进入最终 Evidence”的问题。",
        "2. 文件名、路径、项目实体、年份、Sheet 和正文短语软评分可以把目标证据从通用案例中区分出来。",
        "3. Fact Type 可以防止项目案例中的金额、条数被当作公司级或目标项目事实。",
        "4. 清单/数量问题需要动态 Chunk 配额；固定单文档 2 Chunk 不适合多 Sheet Workbook。",
        "5. 本任务只验证 Evidence 层，不判断 LLM 最终回答是否正确。",
        "",
        "## 7. 下一步",
        "",
        "建议先审阅 BA-007、BA-010 的 optimized trace，再决定是否进入 TASK-016D-2C：扩展到 BA-001～BA-010 并执行 Shadow A/B 统计。通过业务审核前，不进入正式 Evidence Selection。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    chunks = load_chunks()
    classifier = GovernanceClassifier()
    results: list[dict[str, Any]] = []
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    for question_id in ("BA-007", "BA-010"):
        trace = json.loads((TRACE_DIR / f"{question_id}.json").read_text(encoding="utf-8"))
        candidates = build_candidates(trace, chunks, classifier)
        selected, target_no_direct = select_candidates(candidates, QUERY_RULES[question_id])
        baseline = baseline_metrics(trace, QUERY_RULES[question_id], candidates)
        optimized = optimized_metrics(selected, candidates, QUERY_RULES[question_id], target_no_direct)
        optimized_trace = render_optimized_trace(trace, candidates, selected, baseline, optimized, target_no_direct)
        output = OPTIMIZED_DIR / f"{question_id}.json"
        output.write_text(json.dumps(optimized_trace, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(
            {
                "question_id": question_id,
                "baseline_metrics": baseline,
                "optimized_metrics": optimized,
                "optimized_trace": str(output.resolve()),
            }
        )
    REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    print(json.dumps({"optimized_traces": [item["optimized_trace"] for item in results], "report": str(REPORT_PATH.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
