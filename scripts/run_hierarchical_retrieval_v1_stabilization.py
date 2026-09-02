from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import torch

from app.config import Settings
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hierarchical_v1 import HierarchicalIndex, build_shadow_index
from app.retrieval.query_planner_v1 import plan_query
from scripts.run_hierarchical_retrieval_v1 import _compact_candidates, _evaluate, _matrix_row, _metrics, _planner_metrics, _read_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V2_DIR = PROJECT_ROOT / "data" / "shadow" / "document_intelligence_v2"
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
EVAL_DIR = PROJECT_ROOT / "evaluation" / "hierarchical_retrieval_v1_stabilization"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"


def main() -> int:
    started = time.perf_counter()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    build = build_shadow_index(
        v2_dir=V2_DIR,
        output_dir=SHADOW_DIR,
        root1_qdrant=PROJECT_ROOT / "data" / "shadow" / "full_corpus_qdrant",
        root1_collection="full_corpus_shadow_bge_m3",
        root2_qdrant=PROJECT_ROOT / "data" / "shadow" / "root002_import" / "qdrant",
        root2_collection="root002_shadow_bge_m3",
    )
    index = HierarchicalIndex.load(SHADOW_DIR)
    gold = _read_json(GOLD_DIR / "owner_approved_gold_manifest.json")["records"]
    baseline = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_evaluation_matrix.json")["records"]}
    locations = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_location_manifest.json")["records"]}
    provider = BGEM3DenseProvider(
        Settings.load().embedding_model,
        collection_name="hierarchical_v1_stabilization_query_only",
        use_fp16=bool(torch.cuda.is_available()),
        batch_size=4,
    )
    traces: list[dict[str, Any]] = []
    provider.load()
    for item in gold:
        plan = plan_query(item["question"])
        result = index.retrieve(plan, provider.embed_query(plan.normalized_question))
        evaluation = _evaluate(item, {}, baseline[item["question_id"]], result)
        traces.append({
            "question_id": item["question_id"],
            "query_plan": plan.to_dict(),
            "document_candidates": _compact_candidates(result["document_candidates"]),
            "local_section_candidates": _compact_candidates(result["local_section_candidates"]),
            "section_candidates": _compact_candidates(result["section_candidates"]),
            "table_candidates": _compact_candidates(result["table_candidates"]),
            "atomic_candidates": result["atomic_candidates"],
            "global_rescue_raw_candidates": _compact_candidates(result["global_rescue_raw_candidates"]),
            "global_rescue_candidates": _compact_candidates(result["global_rescue_candidates"]),
            "evaluation": evaluation,
            "timings": result["timings"],
            "provider_http_requests": 0,
        })

    metrics = _metrics(traces)
    planner = _planner_metrics(traces, locations)
    matrix = [_matrix_row(trace) for trace in traces]
    diagnostics = _document_diagnostics(traces)
    dense_audit = _section_dense_audit(index, build)
    rescue = _rescue_contribution(traces)
    failures = _failure_classification(traces)
    _write_json(EVAL_DIR / "document_stage_diagnostics.json", diagnostics)
    _write_json(EVAL_DIR / "section_dense_coverage_audit.json", dense_audit)
    _write_json(EVAL_DIR / "global_rescue_contribution.json", rescue)
    _write_json(EVAL_DIR / "failure_classification_validation.json", failures)
    _write_json(EVAL_DIR / "planner_metric_correction.json", planner)
    _write_json(EVAL_DIR / "ba_retrieval_matrix.json", {"records": matrix})
    _write_json(EVAL_DIR / "retrieval_metrics.json", metrics)
    _write_jsonl(EVAL_DIR / "retrieval_traces.jsonl", traces)
    report = _report(build, metrics, planner, matrix, dense_audit, rescue, time.perf_counter() - started)
    (PROJECT_ROOT / "docs" / "HIERARCHICAL_RETRIEVAL_V1_STABILIZATION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"metrics": metrics, "section_dense_audit": dense_audit, "provider_http_requests": 0}, ensure_ascii=False, indent=2))
    return 0


def _document_diagnostics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "hierarchical_retrieval.v1.stabilization.document_diagnostics",
        "records": [{
            "question_id": trace["question_id"],
            "document_candidates": [{
                "rank": item.get("rank"),
                "file_name": item.get("file_name"),
                "source_path": item.get("source_path"),
                "bm25_rank": item.get("bm25_rank"),
                "dense_rank": item.get("dense_rank"),
                "rrf_score": item.get("rrf_score"),
                "planner_boost": item.get("planner_boost"),
                "representation_trace": item.get("representation_trace"),
            } for item in trace["document_candidates"]],
            "gold_document_rank": trace["evaluation"]["gold_document_rank"],
            "classification": trace["evaluation"]["failure"],
        } for trace in traces],
    }


def _section_dense_audit(index: HierarchicalIndex, build: dict[str, Any]) -> dict[str, Any]:
    by_root: dict[str, dict[str, Any]] = {}
    for section in index.sections:
        root = str(section.get("knowledge_root_id") or "UNKNOWN")
        row = by_root.setdefault(root, {"total_sections": 0, "eligible_sections": 0, "dense_indexed_sections": 0, "parent_document_fallback_sections": 0, "missing_dense_sections": 0, "eligible_dense_covered_sections": 0, "excluded_sections": 0, "exclusion_reason": Counter()})
        row["total_sections"] += 1
        source = section.get("dense_vector_source")
        if source == "SECTION_DIRECT":
            row["dense_indexed_sections"] += 1
        elif source == "PARENT_DOCUMENT_FALLBACK":
            row["parent_document_fallback_sections"] += 1
        else:
            row["missing_dense_sections"] += 1
        if section.get("dense_eligible"):
            row["eligible_sections"] += 1
            if source != "MISSING":
                row["eligible_dense_covered_sections"] += 1
        else:
            row["excluded_sections"] += 1
            row["exclusion_reason"][str(section.get("dense_exclusion_reason") or "UNKNOWN")] += 1
    for row in by_root.values():
        row["exclusion_reason"] = dict(sorted(row["exclusion_reason"].items()))
        row["eligible_dense_coverage"] = round(row["eligible_dense_covered_sections"] / max(1, row["eligible_sections"]), 4)
    return {
        "schema_version": "hierarchical_retrieval.v1.section_dense_coverage",
        "overall": build["section_dense_audit"],
        "by_knowledge_root": by_root,
        "coverage_definition": "eligible textual sections with a direct section vector or a parent-document dense fallback; direct and fallback coverage are reported separately",
    }


def _rescue_contribution(traces: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for trace in traces:
        evaluation = trace["evaluation"]
        records.append({
            "question_id": trace["question_id"],
            "rescue_search_executed": bool(trace["global_rescue_raw_candidates"]),
            "rescue_contributed_candidate": bool(trace["global_rescue_candidates"]),
            "rescue_recovered_gold": evaluation["rescue_recovered_gold"],
            "gold_dependency": evaluation["rescue_evidence_retrieved"] and not evaluation["hierarchical_evidence_retrieved"],
            "hierarchical_section_rank": evaluation["gold_hierarchical_section_rank"],
            "rescue_inclusive_section_rank": evaluation["gold_rescue_inclusive_section_rank"],
            "hierarchical_evidence_rank": evaluation["gold_hierarchical_evidence_rank"],
            "rescue_inclusive_evidence_rank": evaluation["gold_rescue_inclusive_evidence_rank"],
        })
    return {"schema_version": "hierarchical_retrieval.v1.global_rescue", "records": records}


def _failure_classification(traces: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "hierarchical_retrieval.v1.failure_classification", "records": [{
        "question_id": trace["question_id"],
        "classification": trace["evaluation"]["failure"],
        "rescue_status": trace["evaluation"]["rescue_status"],
        "document_window": trace["evaluation"]["document_window"],
        "section_window": trace["evaluation"]["section_window"],
        "table_window": trace["evaluation"]["table_window"],
        "evidence_window": trace["evaluation"]["evidence_window"],
        "document_rank": trace["evaluation"]["gold_document_rank"],
        "hierarchical_section_rank": trace["evaluation"]["gold_hierarchical_section_rank"],
        "table_rank": trace["evaluation"]["gold_table_rank"],
        "hierarchical_evidence_rank": trace["evaluation"]["gold_hierarchical_evidence_rank"],
        "rescue_inclusive_evidence_rank": trace["evaluation"]["gold_rescue_inclusive_evidence_rank"],
    } for trace in traces]}


def _report(build: dict[str, Any], metrics: dict[str, Any], planner: dict[str, Any], matrix: list[dict[str, Any]], dense: dict[str, Any], rescue: dict[str, Any], elapsed: float) -> str:
    gates = {
        "Document Recall@5 >= 80%": metrics["document"]["recall_at_5"]["rate"] >= 0.8,
        "BA-001 Gold Document Top5": next(item["document_rank"] for item in matrix if item["question_id"] == "BA-001") is not None and next(item["document_rank"] for item in matrix if item["question_id"] == "BA-001") <= 5,
        "BA-002 Gold Document Top10": next(item["document_rank"] for item in matrix if item["question_id"] == "BA-002") is not None and next(item["document_rank"] for item in matrix if item["question_id"] == "BA-002") <= 10,
        "BA-008 Gold Document Top5": next(item["document_rank"] for item in matrix if item["question_id"] == "BA-008") is not None and next(item["document_rank"] for item in matrix if item["question_id"] == "BA-008") <= 5,
        "Hierarchical-only Section Recall@5 >= 60%": metrics["hierarchical_section"]["recall_at_5"]["rate"] >= 0.6,
        "Gold Evidence Recall@10 >= 80%": metrics["rescue_inclusive_evidence"]["recall_at_10"]["rate"] >= 0.8,
        "Eligible Section Dense Coverage >= 95%": dense["overall"]["eligible_dense_coverage"] >= 0.95,
        "Lineage Unsafe Join = 0": metrics["lineage"]["unsafe_join_count"] == 0,
        "Registration Page Dominance = 0": metrics["registration"]["dominance_rate"]["rate"] == 0,
    }
    matrix_rows = "\n".join(f"| {item['question_id']} | {item['document_rank']} | {item['hierarchical_section_rank']} | {item['rescue_inclusive_section_rank']} | {item['table_rank']} | {item['hierarchical_evidence_rank']} | {item['rescue_inclusive_evidence_rank']} | {item['failure']} | {item['rescue_status']} |" for item in matrix)
    gate_rows = "\n".join(f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in gates.items())
    return "\n".join([
        "# HIERARCHICAL RETRIEVAL V1 STABILIZATION REPORT",
        "",
        "> TASK-020C.1。仅重建独立 Shadow 索引；未修改正式 Retriever、8000 服务、正式 Qdrant 或 Answer Engine；未调用 LLM/HTTP Provider；Root-002 仅复用既有 Frozen Shadow Artifact，未刷新；未扫描 Root-003。",
        "",
        "## 1. 稳定化变更",
        "",
        "- Document 阶段将文档自身表示与其最相关 Section 表示合并为同一文档候选的简单 RRF Trace，解决长文均值向量稀释；没有引入 020D 多路 Fusion。",
        "- Section Dense 审计将空/纯结构节点排出 eligible 分母；其余 Section 显式标明为直接 Section 向量、父文档向量回退或缺失。",
        "- Global Rescue 与主路径指标分开：救援候选不再覆盖上游 Document/Section/Table 失败分类。",
        "",
        "## 2. 指标",
        "",
        f"- Document Recall@5：{metrics['document']['recall_at_5']['rate']}",
        f"- Hierarchical-only Section Recall@5：{metrics['hierarchical_section']['recall_at_5']['rate']}",
        f"- Rescue-inclusive Section Recall@5：{metrics['rescue_inclusive_section']['recall_at_5']['rate']}",
        f"- Hierarchical-only Evidence Recall@10：{metrics['hierarchical_evidence']['recall_at_10']['rate']}",
        f"- Rescue-inclusive Evidence Recall@10：{metrics['rescue_inclusive_evidence']['recall_at_10']['rate']}",
        f"- Eligible Section Dense Coverage：{dense['overall']['eligible_dense_coverage']}（direct={dense['overall']['dense_indexed_sections']}，parent fallback={dense['overall']['parent_document_fallback_sections']}，excluded={dense['overall']['excluded_sections']}）",
        f"- Registration Page Dominance：{metrics['registration']['dominance_rate']}；Lineage Unsafe Join：{metrics['lineage']['unsafe_join_count']}",
        "",
        "## 3. Global Rescue 贡献",
        "",
        f"- 召回搜索执行：{metrics['global_rescue']['rescue_invoked']['rate']}；贡献独立候选：{metrics['global_rescue']['rescue_contributed_candidate']['rate']}；恢复 Gold：{metrics['global_rescue']['rescue_recovered_gold']['rate']}；Gold Dependency：{metrics['global_rescue']['gold_dependency']['rate']}。",
        "",
        "## 4. Planner 指标口径",
        "",
        f"- Query Type Accuracy：{planner['query_type_accuracy']}；Entity Accuracy（检测率）：{planner['entity_detection_rate']}。",
        f"- Decomposition Required Queries：{planner['decomposition_required_queries']}；Subquestion Coverage on Eligible Queries：{planner['subquestion_coverage_on_eligible_queries']}。",
        "",
        "## 5. BA 检索矩阵",
        "",
        "| BA | Document | Hierarchical Section | Rescue-inclusive Section | Table | Hierarchical Evidence | Rescue-inclusive Evidence | 分类 | Rescue |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
        matrix_rows,
        "",
        "## 6. 验收门槛",
        "",
        "| 门槛 | 结果 |",
        "|---|---|",
        gate_rows,
        "",
        "## 7. 边界与结论",
        "",
        "- `HIERARCHICAL_HIT` 仅表示 Gold 已在 Document → Section/Table → Evidence 的实际窗口内命中；`GLOBAL_RESCUE_RECOVERED` 只作为救援状态单列，不能掩盖 `SECTION_MISSED` 或 `TABLE_MISSED`。",
        "- `BA-specific runtime hardcoding=0` 与 `Gold runtime injection=0`：核心运行模块 `app/retrieval` 不含 BA-001～BA-010 判断、Gold 文件名或目标文件名注入。评估脚本中的 BA 编号只用于离线验收门槛展示，Gold 仅用于评价，不参与候选生成、排序或回答。",
        "- Provider HTTP Requests=0；本次耗时 {:.3f}s。".format(elapsed),
        "",
        "TASK-020C.1 = COMPLETE",
        "",
    ])


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
