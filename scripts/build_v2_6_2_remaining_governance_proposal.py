from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_search import query_terms
from app.retrieval.query_planner_v1 import plan_query


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REPLAY = V26 / "v2_6_2_compatibility_replay.json"
CLUSTERS = V26 / "v2_6_2_compatibility_failure_clusters.json"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
OUT = V26 / "v2_6_2_remaining_governance_proposal.json"
REPORT = ROOT / "docs" / "V2_6_2_REMAINING_GOVERNANCE_PROPOSAL.md"
SOURCE_ROOTS = (
    Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2025"),
    Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2026"),
    Path(r"[LOCAL_PATH_REDACTED]��中心"),
)
SUPPORTED = {".md", ".markdown", ".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt"}
SIGNAL_FILES = (
    "台账", "清单", "设计管理经验总结", "设计管理策划", "评审", "检查", "排名", "设计效益增量", "DOP",
    "上半年", "半年运营", "责任清单", "上级单位", "报批报建", "项目设计管理评价", "体系建设", "中心建设",
    "设计能力", "图纸会审", "审核意见", "示范项目", "述职", "设计复盘", "设计评估", "设计管理总结", "汉江", "何棠下", "数据中心", "概算",
)
GENERIC = {
    "项目", "多少", "分别", "其中", "如何", "情况", "共", "哪个", "哪些", "是", "在", "中", "各", "条",
    "提", "主要", "统计", "设计", "价值", "创造", "台账", "策划点", "专业", "共列", "几个", "累计", "一共",
    "包含", "形成", "工作", "内容", "阶段", "涉及", "方面", "当中", "关于", "分别是", "各列", "提了", "有多少",
}
PATH_GENERIC = GENERIC | {
    "公司", "上半年", "年度", "季度", "工作", "设计", "管理", "检查", "评价", "项目", "工程", "内容",
    "通过", "验收", "完成", "关键", "节点", "意见", "提了", "落实", "整体", "2024", "2025", "2026",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def meaningful_terms(question: str) -> list[str]:
    return [
        term.casefold()
        for term in query_terms(question)
        if len(term) >= 2 and term not in GENERIC
    ]


def answer_markers(question: str) -> list[tuple[str, tuple[str, ...]]]:
    markers: list[tuple[str, tuple[str, ...]]] = []
    if any(token in question for token in ("多少钱", "创效", "金额")):
        markers.append(("amount", ("创效", "万元", "金额", "元")))
    if any(token in question for token in ("工期", "多少天", "节约工期")):
        markers.append(("duration", ("工期", "天", "日")))
    if "扣几分" in question or "扣分" in question:
        markers.append(("score", ("扣", "分", "评分")))
    return markers


def physical_candidates(current_paths: set[str]) -> list[Path]:
    return [
        path
        for source_root in SOURCE_ROOTS
        if source_root.is_dir()
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED
        and any(marker.casefold() in str(path).casefold() for marker in SIGNAL_FILES)
        and str(path.resolve()).casefold() not in current_paths
    ]


def evidence_rows(bundle: dict) -> tuple[dict[str, dict], list[dict]]:
    documents = {str(row["document_id"]): row for row in bundle["documents"]}
    rows: list[dict] = []
    for row in bundle["paragraphs"]:
        rows.append({
            "document_id": row["document_id"],
            "kind": "paragraph",
            "evidence_id": row.get("paragraph_id"),
            "text": str(row.get("text") or ""),
            "location": {"paragraph_id": row.get("paragraph_id"), "section_id": row.get("section_id")},
        })
    for row in bundle["table_rows"]:
        values = row.get("values") or row.get("cells") or []
        text = " | ".join(str(value.get("value") if isinstance(value, dict) else value) for value in values)
        rows.append({
            "document_id": row["document_id"],
            "kind": "table_row",
            "evidence_id": row.get("table_row_id") or row.get("row_id"),
            "text": text,
            "location": {"table_id": row.get("table_id"), "row_number": row.get("row_number")},
        })
    return documents, rows


def main() -> int:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    clusters = json.loads(CLUSTERS.read_text(encoding="utf-8"))
    source_gaps = clusters["clusters"]["SOURCE_COVERAGE_OR_EVIDENCE_ROLE_GAP"]
    multi_fact = clusters["clusters"]["MULTI_FACT_COVERAGE_GAP"]
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current_paths = {str(Path(str(row.get("source_path") or "")).resolve()).casefold() for row in current.get("sources") or []}
    paths = physical_candidates(current_paths)

    question_paths: dict[str, list[Path]] = {}
    for item in source_gaps:
        question = str(item.get("question") or "")
        terms = meaningful_terms(question)
        project_terms = meaningful_terms(" ".join(str(value) for value in plan_query(question).project))
        path_terms = [term for term in terms if term not in PATH_GENERIC] or terms
        scored = []
        for path in paths:
            path_text = compact(path)
            if project_terms and not any(term in path_text for term in project_terms):
                continue
            scored.append((sum(term in path_text for term in path_terms), path))
        selected = [
            path
            for score, path in sorted(scored, key=lambda pair: (-pair[0], len(str(pair[1]))))[:2]
            if score > 0
        ]
        question_paths[str(item["question_hash"])] = selected

    # Multi-fact gaps need the same physical-body admission path; otherwise a
    # source can be present only as a link page and never reach the proposal.
    for item in multi_fact:
        question = str(item.get("question") or "")
        terms = meaningful_terms(question)
        preferred = []
        if "哈密" in question and "图纸审查意见" in question:
            preferred = [
                path for path in paths
                if "哈密" in str(path)
                and any(marker in path.name for marker in ("设计管理总结", "设计管理复盘", "图纸会审", "图纸审查", "评审意见"))
            ]
        scored = []
        for path in paths:
            path_text = compact(path)
            score = sum(term in path_text for term in terms)
            if score:
                scored.append((score, path))
        scored_paths = [
            path for score, path in sorted(scored, key=lambda pair: (-pair[0], len(str(pair[1]))))[:3]
            if score > 0
        ]
        question_paths[str(item["question_hash"])] = list(dict.fromkeys([*preferred, *scored_paths]))[:5]

    selected_paths = sorted({path for values in question_paths.values() for path in values}, key=lambda path: str(path).casefold())
    unique_paths: dict[str, Path] = {}
    for path in selected_paths:
        try:
            digest = sha256(path)
        except OSError:
            continue
        unique_paths.setdefault(digest, path)
    selected_paths = sorted(unique_paths.values(), key=lambda path: str(path).casefold())
    bundles: list[dict] = []
    for parent in sorted({path.parent for path in selected_paths}, key=lambda path: str(path).casefold()):
        batch = [path for path in selected_paths if path.parent == parent]
        try:
            bundles.append(DocumentIntelligenceV2Builder(parent).build(batch))
        except Exception:
            continue
    documents: dict[str, dict] = {}
    rows: list[dict] = []
    for bundle in bundles:
        docs, parsed_rows = evidence_rows(bundle)
        documents.update(docs)
        rows.extend(parsed_rows)

    by_question: dict[str, dict[str, dict]] = defaultdict(dict)
    matched_questions: set[str] = set()
    source_gap_hashes = {str(item["question_hash"]) for item in source_gaps}
    for item in [*source_gaps, *multi_fact]:
        question_hash = str(item["question_hash"])
        question = str(item.get("question") or "")
        terms = meaningful_terms(question)
        required_markers = answer_markers(question)
        plan = plan_query(question)
        project_terms = meaningful_terms(" ".join(str(value) for value in plan.project))
        allowed = {path.resolve() for path in question_paths.get(question_hash, [])}
        scored = []
        for row in rows:
            document = documents.get(str(row["document_id"]), {})
            source_path = Path(str(document.get("source_path") or "")).resolve()
            if source_path not in allowed:
                continue
            text = str(row.get("text") or "")
            identity = f"{document.get('file_name', '')} {document.get('source_path', '')}"
            body = compact(text)
            body_term_hits = sum(term in body for term in terms)
            specific_terms = [term for term in terms if len(term) >= 3]
            specific_hits = sum(term in body for term in specific_terms)
            marker_hits = sum(any(marker in body for marker in markers) for _, markers in required_markers)
            project_hits = sum(term in body for term in project_terms)
            # A filename/path hit is registration evidence, not answer evidence.
            # Require the parsed body/table row itself to carry at least one query
            # term so unrelated register rows cannot enter a source-role proposal.
            if body_term_hits < 1 or (specific_terms and specific_hits < 1):
                continue
            if required_markers and marker_hits < len(required_markers):
                continue
            term_hits = body_term_hits
            if term_hits < max(2, min(4, len(terms))) and project_hits < 2:
                continue
            score = term_hits + 2 * project_hits + int(bool(re.search(r"\d", text)))
            scored.append((score, row, document))
        for score, row, document in sorted(scored, key=lambda value: (-value[0], len(value[1]["text"])))[:5]:
            source_path = Path(str(document["source_path"])).resolve()
            key = str(source_path).casefold()
            item_out = by_question[question_hash].setdefault(key, {
                "file_name": document["file_name"],
                "source_path": str(source_path),
                "sha256": sha256(source_path),
                "physical_exists": source_path.is_file(),
                "question_hashes": [],
                "evidence": [],
            })
            if question_hash not in item_out["question_hashes"]:
                item_out["question_hashes"].append(question_hash)
            item_out["evidence"].append({
                "question": question,
                "score": score,
                "kind": row["kind"],
                "evidence_id": row["evidence_id"],
                "location": row["location"],
                "excerpt": row["text"][:700],
            })
            if question_hash in source_gap_hashes:
                matched_questions.add(question_hash)

    records: dict[str, dict] = {}
    for values in by_question.values():
        for key, value in values.items():
            merged = records.setdefault(key, value)
            merged["question_hashes"] = sorted(set(merged["question_hashes"]) | set(value["question_hashes"]))
            merged["evidence"].extend(value["evidence"])
    output_records = []
    for value in sorted(records.values(), key=lambda row: (-len(row["question_hashes"]), row["file_name"])):
        value["question_count"] = len(value["question_hashes"])
        value["approval_status"] = "PENDING_OWNER_APPROVAL"
        value["approval_scope"] = "V2.6.2 missing-content remediation only"
        output_records.append(value)

    payload = {
        "schema_version": "knowledge_os_v2_6_2.remaining_governance_proposal",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": replay.get("current_candidate_hash"),
        "source_gap_question_count": len(source_gaps),
        "multi_fact_gap_question_count": len(multi_fact),
        "selected_physical_file_count": len(selected_paths),
        "source_gap_questions_with_physical_body_match": len(matched_questions),
        "source_count": len(output_records),
        "approval_status": "PENDING_OWNER_APPROVAL",
        "records": output_records,
        "multi_fact_repair_scope": [
            {"question_hash": item["question_hash"], "question": item["question"], "action": "REPAIR_SHARED_COVERAGE_MAP_AND_COMPLETENESS_VALIDATION"}
            for item in multi_fact
        ],
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "note": "Read-only discovery and parse of physical 2026 design-management files; no candidate or runtime write performed.",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text("\n".join([
        "# V2.6.2 剩余治理提案",
        "",
        "> 只读发现与解析结果；不代表来源已批准，不写入候选索引，不切换8010，不启动8000。",
        "",
        f"- 来源/证据角色缺口：`{len(source_gaps)}` 条",
        f"- 多事实覆盖缺口：`{len(multi_fact)}` 条",
        f"- 已发现可解析物理正文对应：`{len(matched_questions)}` 条来源缺口问题",
        f"- 待批准新增物理文件：`{len(output_records)}` 个",
        "",
        "## 处理边界",
        "",
        "1. 仅将物理存在、可解析且能提供正文或表格行证据的文件列入提案。",
        "2. 多事实缺口统一修复共享 coverage map 与完整性校验，不按单题硬编码。",
        "3. 提案中的文件需 Owner 逐批批准后，才能纳入 V2.6.2 候选并重放。",
        "",
    ]), encoding="utf-8")
    print(json.dumps({
        "source_gap_question_count": len(source_gaps),
        "multi_fact_gap_question_count": len(multi_fact),
        "selected_physical_file_count": len(selected_paths),
        "source_gap_questions_with_physical_body_match": len(matched_questions),
        "source_count": len(output_records),
        "out": str(OUT),
        "report": str(REPORT),
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
