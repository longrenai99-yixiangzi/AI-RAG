from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.knowledge_engineering.structured_v2 import build_structured_layer


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
V261_STAGE = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
APPROVED = Path(r"[LOCAL_PATH_REDACTED]")
SOURCES = {
    "b6077e3f74f0a1b7ae9f.md": "c392bc19e997b52f2f31be948ea8876830c0055f612016fd8b1dc119affcb323",
    "沈阳中心大厦工作成果分享.md": "7ce9483b9a83a5a0797c647718e82de2a9e68028a9ffa558c491102d06c29424",
    "海南中心项目塔冠技术交流分享2026.5.27.md": "bcc9a3b8685a86085ce26f1b5163406c6db9801a4258778aee98ee912a5ba082",
    "0ee2959550610ce23750.md": "c921b8c3773304cd2ffef8659812d1498317900cbd8892460454b22a6060f89d",
    "2c5dbe10c9b44d1d47d0.md": "2d2a1005a60aae43465dd06dcb633bcd2ad1b1f3fd2812a7ee3b063e2b030cdc",
    "局2026年半年运营情况分析会暨第二次改革管理论坛上的领导讲话、报告.md": "c78ccf30fb5e64479fba27a4bdf73b6cbc243b4bc31c8a3f2de1415054d48e7c",
    "90b557ce19fb9d757b47.md": "d23adc39ed9e3fd7c13f41b5cb02a9399f813cc902b2c04a9537853586d2ad9e",
    "EPC设计管理经验总结(平鲁风电项目) 2026.5修改.docx": "ace8824935b32b76063df7c894ed7fc70ce358569703715224009b073358770e",
    "design_review_folder_inventory_2026_09_15.md": "2630fbb10fc68341b13bba5395c0c781c54ae4e0ac371a6fd166cd2f07f8feff",
    "丽水医院项目 .docx": "72553e1809d816cf77d787a2184f1dc3c8e73469344e2b1c843a1ed607e3081e",
    "百草园超高层产品线观摩材料.md": "c5dcd9b7346a66bad4cf40873e232c440b69e6e357a83044d8a201da165b59ef",
    "433315cbf3a4f79a6894.md": "b168773319f08591d1cf97943a31834fbcbc1459fd99e04ca6e3e20cb4cf3ac9",
    "西北公司-沣东医院项目经验交流.md": "676dd4b3ef4decf149f9f6138e8f20ed1c9db94262ccf46b61286c777d5a73af",
    "9992d9f7b525192965e4.md": "fe8e3a86250e8d72bdf7f1d6feb445c4f9a2395ca21c30c91f1c5f9a6e4846ba",
    "呼市移动数据中心项目观摩会汇报材料.md": "afe9999cbc700480eb14d494c1dcddf6e11efb52bcacc90d35f6e216fa158868",
    "2025年年度总结.md": "35ec22b164f144b506b83d92947319e14abcea03bab1e0d1d8eeeef7c8443fcd",
    "EPC设计管理经验总结（之寓·保税区人才公寓项目）.docx": "2760e5e2adfba071eab398b92b5501619fa92081009c35a18110a973041381dc",
    "EPC设计管理经验总结(涟水第三水厂建设项目3.17).docx": "a103f5a8c9861c5c753eb77a16e692ce09600179de2db5fe947c0231ac8da138",
    "EPC设计管理经验总结(丰台崔村旧改项目)2026.5.6.docx": "2b738077c1a52520200a5566e2fdec7ac3992b67ee3c29bc54b21a6f9efae64c",
    "EPC设计管理经验总结(泸州垃圾焚烧发电厂项目)20260309.docx": "7fa0d0ef34a3c93d697bd8125a4945a23e8305249e98d5bb6aa8bdc0d74582eb",
    "2024年度总结2.md": "34396ccfd2031f1f7d320d9278b91b2345ca2916d42c5320ce4b1f51377febfc",
    "关于举办新能源项目设计知识的培训通知(1).pdf": "3e3d69d372b4137d42fa8a149bfd639da6783411bf89b34140ef6bf23e7699a6",
    "关于举办设计能力提升季度培训（主体专业设计优化要点）的通知.pdf": "c49ea2cb27e00b6fd4ec6a3da457053be5cfb4f1df131a72d97e4bb3e8f33758",
    "关于举办设计能力提升季度培训（钢结构基坑专项设计知识培训）的通知.pdf": "f07d78b992843d3d53b28489fda507ba892c6ff8a0d1dc9bcb4d77d2a56b70b7",
    "关于举办设计能力提升季度培训（市政桥梁、水厂专项设计知识培训）的通知.pdf": "3500514b3f08d454ba8e317dee34ec1f6f6506a64292ec2967ac7843642cc4f0",
    "萧县厂房项目汇报资料12.14.pptx": "47ee05dc3f06e607081f51d205c5baec29e573efc28b0e1ea59720b745f54ef5",
    # Previously approved sources preserved after the count-based snapshot name collided.
    "武汉国家航天产业基地星谷科创中心建设项目11.14.docx": "6f785865051d472f2e14d50d8e5c2affe726cfd60609cdcea10fba2b39262d42",
    "投标文件.docx": "74d0a52da89faf75260f4be3924b7f54539ae108c7684cb4dba32453e9c5df35",
    "建造业务设计管理体系执行评价表(中船哈密).docx": "bf57ce5db1abf75d1f9293f08d43dfe3f5939e4d392e4f24526c49760ac5c80f",
}
SOURCE_PATH_OVERRIDES = {
    "关于举办新能源项目设计知识的培训通知(1).pdf": Path(r"[LOCAL_PATH_REDACTED]�建设\关于举办新能源项目设计知识的培训通知(1).pdf"),
    "关于举办设计能力提升季度培训（主体专业设计优化要点）的通知.pdf": Path(r"[LOCAL_PATH_REDACTED]�建设\关于举办设计能力提升季度培训（主体专业设计优化要点）的通知.pdf"),
    "关于举办设计能力提升季度培训（钢结构基坑专项设计知识培训）的通知.pdf": Path(r"[LOCAL_PATH_REDACTED]�建设\关于举办设计能力提升季度培训（钢结构基坑专项设计知识培训）的通知.pdf"),
    "关于举办设计能力提升季度培训（市政桥梁、水厂专项设计知识培训）的通知.pdf": Path(r"[LOCAL_PATH_REDACTED]�建设\关于举办设计能力提升季度培训（市政桥梁、水厂专项设计知识培训）的通知.pdf"),
    "萧县厂房项目汇报资料12.14.pptx": Path(r"[LOCAL_PATH_REDACTED]�房项目汇报资料12.14.pptx"),
    "武汉国家航天产业基地星谷科创中心建设项目11.14.docx": Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2025\投标\武汉国家航天产业基地星谷科创中心建设项目11.14.docx"),
    "投标文件.docx": Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2025\季度检查\四季度\光谷实验中学\3设计评估管理\投标文件.docx"),
    "建造业务设计管理体系执行评价表(中船哈密).docx": Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2025\季度检查\四季度\建造业务设计管理体系执行评价表(中船哈密).docx"),
}
SOURCE_ROLE_APPROVAL_BATCH = V26 / "v2_6_2_source_role_approval_batch.json"
MISSING_CONTENT_PROPOSAL = V26 / "v2_6_2_missing_content_source_proposal.json"
REMAINING_SOURCE_PROPOSAL = V26 / "v2_6_2_remaining_source_proposal.json"
REMAINING_GOVERNANCE_PROPOSAL = V26 / "v2_6_2_remaining_governance_proposal.json"
CURRENT_CANDIDATE = V26 / "remediation_candidate_v2_6_2.json"
PRIOR_SOURCE_RECOVERY = V26 / "v2_6_2_prior_candidate_source_recovery.json"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    source_records = [{"file_name": name, "path": SOURCE_PATH_OVERRIDES.get(name, APPROVED / name), "sha256": digest} for name, digest in SOURCES.items()]
    if CURRENT_CANDIDATE.exists():
        current_candidate = json.loads(CURRENT_CANDIDATE.read_text(encoding="utf-8"))
        for item in current_candidate.get("sources") or []:
            path = Path(str(item.get("source_path") or ""))
            digest = str(item.get("sha256") or "")
            if path and digest:
                source_records.append({"file_name": path.name, "path": path, "sha256": digest})
    if PRIOR_SOURCE_RECOVERY.exists():
        recovery = json.loads(PRIOR_SOURCE_RECOVERY.read_text(encoding="utf-8"))
        for item in recovery.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            digest = str(item.get("sha256") or "")
            if path and digest:
                source_records.append({"file_name": path.name, "path": path, "sha256": digest})
    if SOURCE_ROLE_APPROVAL_BATCH.exists():
        batch = json.loads(SOURCE_ROLE_APPROVAL_BATCH.read_text(encoding="utf-8"))
        if batch.get("approval_status") == "PENDING_OWNER_APPROVAL":
            raise RuntimeError("SOURCE_ROLE_APPROVAL_BATCH_PENDING")
        for item in batch.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            if not item.get("sha256") or not path:
                continue
            source_records.append({"file_name": path.name, "path": path, "sha256": str(item["sha256"])})
    if MISSING_CONTENT_PROPOSAL.exists():
        proposal = json.loads(MISSING_CONTENT_PROPOSAL.read_text(encoding="utf-8"))
        if proposal.get("approval_status") == "PENDING_OWNER_APPROVAL":
            raise RuntimeError("MISSING_CONTENT_SOURCE_PROPOSAL_PENDING")
        for item in proposal.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            if not item.get("sha256") or not path:
                continue
            source_records.append({"file_name": path.name, "path": path, "sha256": str(item["sha256"])})
    if REMAINING_SOURCE_PROPOSAL.exists():
        proposal = json.loads(REMAINING_SOURCE_PROPOSAL.read_text(encoding="utf-8"))
        if proposal.get("approval_status") == "PENDING_OWNER_APPROVAL":
            raise RuntimeError("REMAINING_SOURCE_PROPOSAL_PENDING")
        for item in proposal.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            if not item.get("sha256") or not path:
                continue
            source_records.append({"file_name": path.name, "path": path, "sha256": str(item["sha256"])})
    for proposal_path in sorted(V26.glob("v2_6_2_*source_proposal_approved*.json"), key=lambda path: str(path).casefold()):
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        if proposal.get("approval_status") != "APPROVED":
            continue
        for item in proposal.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            if not item.get("sha256") or not path:
                continue
            source_records.append({"file_name": path.name, "path": path, "sha256": str(item["sha256"])})
    for proposal_path in sorted(V26.glob("v2_6_2_*governance_proposal*.json"), key=lambda path: str(path).casefold()):
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        if proposal.get("approval_status") != "APPROVED":
            continue
        for item in proposal.get("records") or []:
            path = Path(str(item.get("source_path") or ""))
            if not item.get("sha256") or not path:
                continue
            source_records.append({"file_name": path.name, "path": path, "sha256": str(item["sha256"])})
    deduped: dict[str, dict] = {}
    for record in source_records:
        deduped[str(record["path"].resolve()).casefold()] = record
    source_records = list(deduped.values())
    paths = [record["path"] for record in source_records]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(missing)
    mismatched = [{"path": str(record["path"]), "expected": record["sha256"], "actual": _sha(record["path"])} for record in source_records if _sha(record["path"]) != record["sha256"]]
    if mismatched:
        raise RuntimeError(f"SOURCE_SHA256_MISMATCH:{mismatched}")
    builder = DocumentIntelligenceV2Builder(APPROVED.parents[1])
    atomic = []
    for path in paths:
        atomic.extend(build_atomic_evidence(path, APPROVED.parents[1]).get("records") or [])
    parsed = builder.build(paths, atomic)
    registry = {}
    admitted = []
    digest_by_path = {str(record["path"].resolve()).casefold(): record["sha256"] for record in source_records}
    for path in paths:
        digest = digest_by_path[str(path.resolve()).casefold()]
        source_id = "V262-" + hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
        registry[str(path).casefold()] = {"source_id": source_id, "source_path": str(path), "current_hash": digest, "body_status": "APPROVED_DEV_REMEDIATION", "index_status": "DEV_REMEDIATION_ONLY"}
        admitted.append({"source_id": source_id, "source_path": str(path), "file_name": path.name, "sha256": digest, "approval_status": "APPROVED", "approved_by": "USER_CONFIRMED"})
    for document in parsed["documents"]:
        path = Path(str(document.get("source_path") or ""))
        document.update({"source_id": registry[str(path).casefold()]["source_id"], "source_version": digest_by_path[str(path.resolve()).casefold()], "source_hash": digest_by_path[str(path.resolve()).casefold()], "effective_status": "APPROVED_DEV_REMEDIATION"})
    layer = build_structured_layer(parsed["documents"], parsed["sections"], parsed["paragraphs"], parsed["tables"], parsed["table_rows"], parsed["atomic_evidence"], registry)
    STAGING.mkdir(parents=True, exist_ok=True)
    for name in ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts", "atomic_evidence"):
        old = _read_jsonl(V261_STAGE / f"{name}.jsonl")
        _write_jsonl(STAGING / f"{name}.jsonl", [*old, *(parsed.get(name) or [])])
    old_chunks = _read_jsonl(V261_STAGE / "semantic_chunks.jsonl")
    _write_jsonl(STAGING / "semantic_chunks.jsonl", [*old_chunks, *layer["semantic_chunks"]])
    _write_jsonl(STAGING / "knowledge_node_bindings.jsonl", [*_read_jsonl(V261_STAGE / "knowledge_node_bindings.jsonl"), *layer["knowledge_node_bindings"]])
    shutil.copyfile(V261_STAGE / "dense_embeddings.npy", STAGING / "dense_embeddings_v2_6_1.npy")
    now = datetime.now(timezone.utc).astimezone().isoformat()
    manifest = {
        "schema_version": "knowledge_os_v2_6_2.dev_remediation_candidate",
        "candidate_id": "V2.6.2-DEV-SOURCE-COVERAGE",
        "captured_at": now,
        "status": "DEV_REMEDIATION_PENDING_EMBEDDING",
        "base_candidate_hash": json.loads((V26 / "remediation_candidate_v2_6_1.json").read_text(encoding="utf-8"))["candidate_hash"],
        "candidate_revision": "V2.6.2_DEV_SOURCE_COVERAGE",
        "source_count_added": len(paths),
        "sources": admitted,
        "parse_counts_added": {name: len(parsed.get(name) or []) for name in ("documents", "sections", "paragraphs", "tables", "table_rows", "atomic_evidence", "metadata_conflicts")},
        "semantic_chunks": {"base_v2_6_1": len(old_chunks), "added": len(layer["semantic_chunks"]), "total": len(old_chunks) + len(layer["semantic_chunks"]), "path": str(STAGING / "semantic_chunks.jsonl")},
        "embedding_status": "PENDING_NEW_SOURCE_EMBEDDING",
        "formal_8000_touched": False,
        "8010_switch_performed": False,
        "approval_scope": "User approved all listed SHA-256 versions for V2.6.2 source-role remediation only.",
    }
    (V26 / "remediation_candidate_v2_6_2.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "remediation_source_approval_v2_6_2.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_6_2.source_approval", "captured_at": now, "approval_status": "APPROVED", "approved_by": "USER_CONFIRMED", "records": admitted, "formal_8000_touched": False, "8010_switch_authorized": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    if SOURCE_ROLE_APPROVAL_BATCH.exists():
        batch = json.loads(SOURCE_ROLE_APPROVAL_BATCH.read_text(encoding="utf-8"))
        batch.update({"captured_at": now, "approval_status": "APPROVED", "approved_by": "USER_CONFIRMED", "approved_scope": "V2.6.2 source-role remediation only"})
        for item in batch.get("records") or []:
            item.update({"approval_status": "APPROVED", "approved_by": "USER_CONFIRMED"})
        SOURCE_ROLE_APPROVAL_BATCH.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "source_count_added": len(paths), "parse_counts_added": manifest["parse_counts_added"], "semantic_chunks": manifest["semantic_chunks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
