from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import torch
import yaml
from qdrant_client import QdrantClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import select_evidence_optimized
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.bm25 import BM25Index
from app.config import Settings
from app.domain import Chunk, SearchHit
from app.ingestion.metadata.governance import GovernanceClassifier
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.shadow_precision import analyze_precision_intent


ROOT_ID = "Root-002"
COLLECTION = "root002_shadow_bge_m3"
DEFAULT_SHADOW = Path("data") / "shadow" / "root002_import"
DEFAULT_GOLD = Path("tests") / "gold_questions" / "business_acceptance_10.yaml"
DEFAULT_AUDIT = Path("docs") / "BUSINESS_QUERY_FAILURE_AUDIT.md"

ROOT2_RELEVANCE_TERMS = {
    "BA-001": (),
    "BA-002": (),
    "BA-003": ("厂房", "产品线方案比选", "厂房产品线"),
    "BA-004": ("喷淋", "管材", "PVC-C", "镀锌钢管"),
    "BA-005": ("集电线路", "特殊环境", "电气设计图审"),
    "BA-006": ("DOP", "责任状", "电子图形文件", "上传数量"),
    "BA-007": ("设计示范项目", "示范项目打造", "设计与技术工作计划"),
    "BA-008": ("2025", "设计创效", "创效金额"),
    # The actual BA-009 question is about a biweekly EPC meeting, not the ledger file.
    "BA-009": ("双周推进", "土木公司", "督办"),
    "BA-010": ("新洲星谷", "星谷科创中心", "设计价值创造", "价值创造清单"),
}
ROOT2_FOCUS_FILE_TERMS = {
    "BA-007": ("中建三局2026年设计与技术工作计划", "设计与技术工作计划"),
    "BA-009": ("公司设计服务管理台帐2026", "设计服务管理台账"),
    "BA-010": ("方案比选与价值创造清单方案比选及价值创造", "设计管理策划书-星谷科创中心项目"),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_questions(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [item for item in payload.get("questions", []) if str(item.get("id", "")).startswith("BA-")]


def load_old_audit(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"\|\s*(BA-\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            result[match.group(1)] = {
                "status": match.group(2).strip(),
                "root_cause": match.group(3).strip(),
            }
    return result


def build_chunks(staging: list[dict[str, Any]]) -> tuple[list[Chunk], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    chunks: list[Chunk] = []
    metadata_by_chunk: dict[str, dict[str, Any]] = {}
    chunk_source: dict[str, dict[str, Any]] = {}
    for document in staging:
        for item in document.get("chunks", []):
            chunk = Chunk(**item)
            chunks.append(chunk)
            metadata_by_chunk[chunk.chunk_id] = dict(
                document.get("chunk_metadata", {}).get(chunk.chunk_id)
                or document.get("metadata", {})
            )
            chunk_source[chunk.chunk_id] = {
                "source_record_id": document.get("source_record_id"),
                "knowledge_root_id": document.get("knowledge_root_id"),
                "file_name": chunk.file_name,
                "source_path": chunk.source_path,
            }
    return chunks, metadata_by_chunk, chunk_source


class Root002DenseSearch:
    def __init__(self, client: QdrantClient, provider: BGEM3DenseProvider) -> None:
        self.client = client
        self.provider = provider

    def search(self, question: str, limit: int) -> list[tuple[str, float]]:
        vector = self.provider.embed_query(question)
        response = self.client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            (str((point.payload or {}).get("chunk_id") or point.id), float(point.score))
            for point in response.points
        ]


def text_for(chunk: Chunk) -> str:
    return f"{chunk.file_name} {chunk.source_path} {chunk.heading_path} {chunk.text}".casefold()


def matching_chunks(chunks: list[Chunk], terms: tuple[str, ...]) -> list[Chunk]:
    if not terms:
        return []
    return [chunk for chunk in chunks if _matches_relevance(text_for(chunk), terms)]


def _matches_relevance(searchable: str, terms: tuple[str, ...]) -> bool:
    """Use question-specific term combinations; one generic word is not evidence."""
    if not terms:
        return False
    if "厂房" in terms:
        return "厂房" in searchable and "产品线" in searchable and "方案比选" in searchable
    if "喷淋" in terms:
        return (
            ("喷淋" in searchable or "自动喷淋" in searchable)
            and ("pvc-c" in searchable or "镀锌钢管" in searchable)
        )
    if "集电线路" in terms:
        return (
            "集电线路" in searchable
            and "特殊环境" in searchable
            and "电气" in searchable
            and "图审" in searchable
        )
    if "DOP" in terms:
        return "dop" in searchable and "责任状" in searchable and "电子图形文件" in searchable
    if "设计示范项目" in terms:
        return ("设计示范项目" in searchable or "示范项目打造" in searchable) and "2026" in searchable
    if "2025" in terms:
        return "2025" in searchable and ("公司设计创效" in searchable or "创效金额" in searchable)
    if "双周推进" in terms:
        return "双周推进" in searchable and ("土木" in searchable or "督办" in searchable)
    if "新洲星谷" in terms:
        return ("新洲星谷" in searchable or "星谷科创中心" in searchable) and (
            "价值创造" in searchable or "方案比选" in searchable
        )
    return any(term.casefold() in searchable for term in terms)


def match_ids(items: list[dict[str, Any]], terms: tuple[str, ...]) -> list[str]:
    if not terms:
        return []
    return [
        str(item.get("chunk_id"))
        for item in items
        if any(term.casefold() in str(item.get("excerpt", "")).casefold() or term.casefold() in str(item.get("file_name", "")).casefold() for term in terms)
    ]


def source_summary(bundle: Any) -> list[dict[str, Any]]:
    return [
        {
            "source_id": item.source_id,
            "chunk_id": item.chunk_id,
            "file_name": item.file_name,
            "source_path": item.source_path,
            "document_role": item.document_role,
            "authority_level": item.authority_level,
            "location": item.location,
            "excerpt": item.excerpt,
            "retrieval_score": item.retrieval_score,
        }
        for item in bundle.items
    ]


def evidence_relevance(
    question_id: str,
    hits: list[SearchHit],
    bundle: Any,
    chunks: list[Chunk],
) -> dict[str, Any]:
    terms = ROOT2_RELEVANCE_TERMS.get(question_id, ())
    focus_terms = ROOT2_FOCUS_FILE_TERMS.get(question_id, ())
    matching = matching_chunks(chunks, terms)
    top_ids = {hit.chunk.chunk_id for hit in hits}
    evidence_ids = {item.chunk_id for item in bundle.items}
    matching_ids = {chunk.chunk_id for chunk in matching}
    matching_files = sorted({chunk.file_name for chunk in matching})
    focus_files = sorted(
        {
            chunk.file_name
            for chunk in chunks
            if any(term.casefold() in text_for(chunk) for term in focus_terms)
        }
    )
    top_match = bool(top_ids & matching_ids)
    evidence_match = bool(evidence_ids & matching_ids)
    return {
        "relevance_terms": list(terms),
        "root2_answer_bearing_chunk_count_by_keyword": len(matching),
        "root2_answer_bearing_files_by_keyword": matching_files[:20],
        "root2_relevant_top_hit": top_match,
        "root2_relevant_evidence": evidence_match,
        "root2_focus_file_terms": list(focus_terms),
        "root2_focus_files_in_shadow": focus_files[:20],
        "focus_file_in_top_evidence": any(
            any(term.casefold() in f"{item.file_name} {item.source_path}".casefold() for term in focus_terms)
            for item in bundle.items
        ),
    }


def new_failure_reason(
    *,
    response_status: str,
    relevance: dict[str, Any],
    bundle: Any,
    provider_error: str | None,
) -> str:
    if response_status == "LLM_ERROR":
        return "LLM_ERROR：Provider调用失败"
    if response_status == "STRUCTURE_INVALID":
        return "ANSWER_ENGINE_STRUCTURE_FAILURE：检索证据已给出，但输出结构仍失败"
    if relevance["root2_relevant_evidence"] is False:
        if relevance["root2_answer_bearing_chunk_count_by_keyword"] == 0:
            return "ROOT002_SCOPE_MISSING：批准范围内未发现该问题的答案特征资料"
        return "RETRIEVAL_OR_EVIDENCE_SELECTION_FAILURE：Shadow中存在关键词资料，但未进入证据包"
    if response_status == "NO_EVIDENCE" and relevance["root2_relevant_evidence"] and bundle.items:
        return "ANSWER_ENGINE_NO_CLAIM：相关证据已进入证据包，但最终没有形成有效 Claim"
    if response_status == "NO_EVIDENCE" or not bundle.items:
        return "NO_EVIDENCE：未形成可回答证据"
    if response_status == "PARTIAL_EVIDENCE":
        return "ANSWER_ENGINE_OR_EVIDENCE_INSUFFICIENT：证据已召回但回答仍不完整"
    return "NONE"


def render_report(
    *,
    rows: list[dict[str, Any]],
    old: dict[str, dict[str, str]],
    shadow_dir: Path,
    qdrant_count: int,
    provider_available: bool,
    provider_error: str | None,
) -> str:
    recovered = [row for row in rows if row["recovered"]]
    failed = [row for row in rows if row["still_failed"]]
    lines = [
        "# Business Query Regression Report",
        "",
        "> TASK-016C-3 基于 BA-001～BA-010，对 Root-002 独立 Shadow Collection 做回归验证。",
        "> 本次不修改正式 Retriever、Answer Engine、8000 服务或正式 Qdrant；不调整模型参数。",
        "",
        "## 1. 测试口径",
        "",
        f"- Shadow 路径：`{shadow_dir.resolve()}`",
        f"- Shadow Collection：`{COLLECTION}`",
        f"- Shadow Qdrant 点数：`{qdrant_count}`",
        "- 检索：Root-002 staging 上的 BM25 + BGE-M3 Dense + RRF；没有写入其他 Collection。",
        "- Answer Status：调用现有 Shadow Answer Engine 生成；未修改其代码和 Schema。",
        f"- LLM Provider 可用：`{provider_available}`；错误：`{provider_error or '无'}`",
        "",
        "### 重要边界",
        "",
        "`Root-002命中`分两层记录：Shadow Collection 中的所有结果都属于 Root-002；真正用于判断修复是否生效的是`Root-002相关资料命中`，即 Top Evidence 是否包含该问题对应的答案特征或批准文件。",
        "",
        "## 2. 十题回归对比",
        "",
        "| 问题 | Intent | TASK-016A旧状态 | C-3新状态 | Root-002相关资料命中 | 是否仍失败 | 失败原因变化 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['question_id']} | {row['intent']} | {row['old_status']} | {row['new_status']} | "
            f"{row['relevance']['root2_relevant_evidence']} | {row['still_failed']} | {row['failure_reason']} |"
        )
    lines += [
        "",
        f"- 恢复数量：**{len(recovered)}**",
        f"- 仍失败数量：**{len(failed)}**",
        f"- 新状态分布：`{json.dumps(dict(Counter(row['new_status'] for row in rows)), ensure_ascii=False)}`",
        "",
        "## 3. 逐题结果",
        "",
    ]
    for row in rows:
        lines += [
            f"### {row['question_id']}｜{row['question']}",
            "",
            f"- Intent：`{row['intent']}`",
            f"- Answer Status：`{row['new_status']}`",
            f"- TASK-016A：`{row['old_status']}`；旧根因：`{row['old_root_cause']}`",
            f"- Root-002 Shadow 相关命中：`{row['relevance']['root2_relevant_evidence']}`",
            f"- Root-002答案特征 Chunk 数：`{row['relevance']['root2_answer_bearing_chunk_count_by_keyword']}`",
            f"- 是否仍失败：`{row['still_failed']}`",
            f"- 新失败原因：{row['failure_reason']}",
            "",
            "#### Top Evidence",
            "",
        ]
        if row["top_evidence"]:
            for item in row["top_evidence"]:
                lines += [
                    f"- `{item['source_id']}` `{item['file_name']}`｜role=`{item['document_role']}`｜authority=`{item['authority_level']}`",
                    f"  - Source：`{item['source_path']}`",
                    f"  - Location：`{json.dumps(item['location'], ensure_ascii=False)}`",
                    f"  - Excerpt：{item['excerpt'][:320].replace(chr(10), ' ')}",
                ]
        else:
            lines.append("- 无 Evidence Bundle。")
        lines += [
            "",
            "#### Document Source",
            "",
        ]
        for source in row["document_sources"]:
            lines.append(f"- `{source}`")
        if not row["document_sources"]:
            lines.append("- 无")
        lines += ["", "---", ""]
    lines += [
        "## 4. 重点问题专项结论",
        "",
        "### BA-007：2026年设计示范项目的打造要求",
        "",
        _focus_text(rows, "BA-007"),
        "",
        "### BA-009：设计服务管理台账/双周推进督办",
        "",
        _focus_text(rows, "BA-009"),
        "",
        "> 口径冲突：Gold Dataset 中 BA-009 的真实问题是“2026年4月EPC项目双周推进会上，给土木公司的督办是什么？”，而 TASK-016C-2/本任务重点文字将 BA-009 描述为“设计服务管理台账”。本报告按 Gold Dataset 的原始问题执行，不能用台账文件命中替代双周推进督办证据。",
        "",
        "### BA-010：星谷价值创造清单",
        "",
        _focus_text(rows, "BA-010"),
        "",
        "## 5. 根因变化统计",
        "",
        "| 旧根因 | 新结果 | 数量 | 问题 |",
        "|---|---|---:|---|",
    ]
    grouped: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        grouped.setdefault((row["old_root_cause"], row["failure_reason"]), []).append(row["question_id"])
    for (old_reason, new_reason), ids in sorted(grouped.items()):
        lines.append(f"| {old_reason} | {new_reason} | {len(ids)} | {', '.join(ids)} |")
    lines += [
        "",
        "## 6. 下一步修复建议",
        "",
        "1. 对 BA-007、BA-010：将本次已验证可解析并入 Shadow 的外部正文纳入后续受控发布候选，但先做业务内容审核和版本确认。",
        "2. 对 BA-009：先解决问题定义与资料对应关系，确认到底验收“设计服务管理台账”还是“2026年4月EPC双周推进督办”。",
        "3. 对仍无相关资料的 BA-001～BA-006、BA-008：不能把 Root-002 未命中判定为系统错误，应回到 Root-001/Root-003 或其他待审批 Root 继续做源文件闭环。",
        "4. 对 Evidence 已命中但仍为 PARTIAL_EVIDENCE/STRUCTURE_INVALID 的题目，再单独进入 Answer Engine 诊断；本次不修改 Answer Engine。",
        "",
    ]
    return "\n".join(lines)


def _focus_text(rows: list[dict[str, Any]], question_id: str) -> str:
    row = next(item for item in rows if item["question_id"] == question_id)
    if row["relevance"]["root2_relevant_evidence"] and row["relevance"]["focus_file_in_top_evidence"]:
        conclusion = "目标文件和相关证据均已进入证据包；仍需人工确认回答内容是否完整。"
    elif row["relevance"]["root2_relevant_evidence"]:
        conclusion = "Root-002 中存在相关资料，但目标文件未进入 Top Evidence；源文件闭环已建立，检索/证据选择仍需修复。"
    elif row["relevance"]["focus_file_in_top_evidence"]:
        conclusion = "目标文件已被召回，但答案特征片段未进入证据包；检索/证据选择仍需修复。"
    else:
        conclusion = "本次未找回能直接支撑该问题的 Root-002 证据。"
    return (
        f"- 原始问题：{row['question']}\n"
        f"- 新状态：`{row['new_status']}`\n"
        f"- 重点文件是否出现在 Top Evidence：`{row['relevance']['focus_file_in_top_evidence']}`\n"
        f"- Shadow 中匹配的重点文件：`{', '.join(row['relevance']['root2_focus_files_in_shadow']) or '无'}`\n"
        f"- 结论：{conclusion}"
    )


def replay_rows(raw_rows: list[dict[str, Any]], chunks: list[Chunk], old: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """Recompute deterministic relevance flags without another retrieval or LLM call."""
    rows: list[dict[str, Any]] = []
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    for raw in raw_rows:
        items = raw.get("evidence_bundle", {}).get("items", [])
        item_ids = {str(item.get("chunk_id")) for item in items}
        terms = ROOT2_RELEVANCE_TERMS.get(str(raw["question_id"]), ())
        focus_terms = ROOT2_FOCUS_FILE_TERMS.get(str(raw["question_id"]), ())
        matches = [chunk for chunk in chunks if _matches_relevance(text_for(chunk), terms)]
        matching_ids = {chunk.chunk_id for chunk in matches}
        relevance = {
            "relevance_terms": list(terms),
            "root2_answer_bearing_chunk_count_by_keyword": len(matches),
            "root2_answer_bearing_files_by_keyword": sorted({chunk.file_name for chunk in matches})[:20],
            "root2_relevant_top_hit": bool(item_ids & matching_ids),
            "root2_relevant_evidence": bool(item_ids & matching_ids),
            "root2_focus_file_terms": list(focus_terms),
            "root2_focus_files_in_shadow": sorted(
                {
                    chunk.file_name
                    for chunk in chunks
                    if any(term.casefold() in chunk.file_name.casefold() for term in focus_terms)
                }
            )[:20],
            "focus_file_in_top_evidence": any(
                any(term.casefold() in f"{item.get('file_name', '')} {item.get('source_path', '')}".casefold() for term in focus_terms)
                for item in items
            ),
        }
        status = str(raw.get("answer_status") or "NOT_RECORDED")
        bundle_proxy = SimpleNamespace(items=items)
        failed = status != "GENERATED" or not relevance["root2_relevant_evidence"]
        rows.append(
            {
                "question_id": str(raw["question_id"]),
                "question": str(raw["question"]),
                "intent": str(raw.get("intent") or "NOT_RECORDED"),
                "intent_metadata_hints": {},
                "old_status": old.get(str(raw["question_id"]), {}).get("status", "NOT_RECORDED"),
                "old_root_cause": old.get(str(raw["question_id"]), {}).get("root_cause", "NOT_RECORDED"),
                "new_status": status,
                "top_evidence": items,
                "document_sources": sorted({str(item.get("source_path")) for item in items if item.get("source_path")}),
                "root2_collection_hit": bool(items),
                "relevance": relevance,
                "still_failed": failed,
                "recovered": not failed,
                "failure_reason": new_failure_reason(
                    response_status=status,
                    relevance=relevance,
                    bundle=bundle_proxy,
                    provider_error=None,
                ),
                "retrieval_debug": raw.get("retrieval_debug", {}),
                "answer_text": raw.get("answer_text", ""),
                "response_error": raw.get("error"),
                "response_diagnostics": raw.get("diagnostics", {}),
            }
        )
    return sorted(rows, key=lambda row: row["question_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BA-001 to BA-010 against Root-002 Shadow only")
    parser.add_argument("--shadow-dir", type=Path, default=DEFAULT_SHADOW)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--replay", type=Path, default=None, help="回放已持久化结果，不重新检索或调用 LLM")
    args = parser.parse_args()

    staging = read_jsonl(args.shadow_dir / "pipeline_staging.jsonl")
    questions = load_questions(args.gold)
    if {str(item.get("id")) for item in questions} != {f"BA-{index:03d}" for index in range(1, 11)}:
        raise ValueError("BA Gold Dataset 必须完整包含 BA-001 至 BA-010")
    old = load_old_audit(args.audit)
    chunks, metadata_by_chunk, _ = build_chunks(staging)
    if not chunks:
        raise ValueError("Root-002 Shadow staging 没有 Chunk")

    qdrant_dir = args.shadow_dir / "qdrant"
    client = QdrantClient(path=str(qdrant_dir))
    qdrant_count = client.count(collection_name=COLLECTION, exact=True).count
    if args.replay:
        rows = replay_rows(read_jsonl(args.replay), chunks, old)
        report = render_report(
            rows=rows,
            old=old,
            shadow_dir=args.shadow_dir,
            qdrant_count=qdrant_count,
            provider_available=Settings.load().api_ready,
            provider_error=None,
        )
        report_path = Path("docs") / "BUSINESS_QUERY_REGRESSION_REPORT.md"
        report_path.write_text(report, encoding="utf-8")
        client.close()
        print(json.dumps({"recovered": sum(row["recovered"] for row in rows), "still_failed": sum(row["still_failed"] for row in rows), "replayed": str(args.replay), "report": str(report_path.resolve())}, ensure_ascii=False, indent=2))
        return 0
    settings = Settings.load()
    provider = OpenAICompatibleProvider(settings)
    generator = ShadowAnswerGenerator(provider)

    classifier = GovernanceClassifier()
    governance_by_chunk = {
        chunk.chunk_id: classifier.classify(
            file_name=chunk.file_name,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
            metadata=metadata_by_chunk.get(chunk.chunk_id, {}),
        )
        for chunk in chunks
    }
    bm25 = BM25Index(args.shadow_dir / "root002_bm25_runtime.json")
    bm25.build(chunks)
    dense_provider = BGEM3DenseProvider(
        PROJECT_ROOT / "models" / "bge-m3",
        collection_name=COLLECTION,
        use_fp16=True,
        batch_size=4,
    )
    dense_provider.load()
    dense = Root002DenseSearch(client, dense_provider)
    retriever = HybridRetriever(bm25, chunks, dense=dense)

    rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    try:
        for question in sorted(questions, key=lambda item: str(item["id"])):
            question_id = str(question["id"])
            text = str(question["question"])
            intent = analyze_precision_intent(text)
            policy = policy_for_intent(intent.question_type)
            retrieval = retriever.search(text, bm25_limit=20, dense_limit=20, rerank_limit=20, final_limit=10)
            bundle = select_evidence_optimized(
                retrieval.hits,
                policy,
                governance_by_chunk,
                max_items=5,
            )
            response = generator.generate(text, policy, bundle)
            relevance = evidence_relevance(question_id, retrieval.hits, bundle, chunks)
            failed = response.status != "GENERATED" or relevance["root2_relevant_evidence"] is False
            reason = new_failure_reason(
                response_status=response.status,
                relevance=relevance,
                bundle=bundle,
                provider_error=provider.last_error,
            )
            source_list = sorted({item.source_path for item in bundle.items})
            row = {
                "question_id": question_id,
                "question": text,
                "intent": intent.question_type,
                "intent_metadata_hints": intent.metadata_hints,
                "old_status": old.get(question_id, {}).get("status", "NOT_RECORDED"),
                "old_root_cause": old.get(question_id, {}).get("root_cause", "NOT_RECORDED"),
                "new_status": response.status,
                "top_evidence": source_summary(bundle),
                "document_sources": source_list,
                "root2_collection_hit": bool(retrieval.hits),
                "relevance": relevance,
                "still_failed": failed,
                "recovered": not failed,
                "failure_reason": reason,
                "retrieval_debug": retrieval.debug,
                "answer_text": response.answer_text,
                "response_error": response.error,
                "response_diagnostics": response.diagnostics,
            }
            rows.append(row)
            raw_rows.append(
                {
                    "question_id": question_id,
                    "question": text,
                    "intent": intent.question_type,
                    "retrieval_debug": retrieval.debug,
                    "evidence_bundle": asdict(bundle),
                    "answer_status": response.status,
                    "answer_text": response.answer_text,
                    "raw_llm_response": response.raw_llm_response,
                    "parsed_response": response.parsed_response,
                    "repair_response": response.repair_response,
                    "error": response.error,
                    "diagnostics": response.diagnostics,
                    "relevance": relevance,
                }
            )
            print(f"business_query_progress={len(rows)}/10", flush=True)
    finally:
        dense_provider.close()
        client.close()

    output_jsonl = args.shadow_dir / "business_query_regression_outputs.jsonl"
    output_jsonl.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in raw_rows),
        encoding="utf-8",
    )
    report = render_report(
        rows=rows,
        old=old,
        shadow_dir=args.shadow_dir,
        qdrant_count=qdrant_count,
        provider_available=provider.available,
        provider_error=provider.last_error,
    )
    report_path = Path("docs") / "BUSINESS_QUERY_REGRESSION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "recovered": sum(row["recovered"] for row in rows),
                "still_failed": sum(row["still_failed"] for row in rows),
                "status_counts": dict(Counter(row["new_status"] for row in rows)),
                "output": str(output_jsonl.resolve()),
                "report": str(report_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
