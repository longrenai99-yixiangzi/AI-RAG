"""T01: bind V2 chunks to existing framework nodes plus explicit rule candidates."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
OUT = ROOT / "evaluation" / "knowledge_os_v2_2" / "node_binding"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def node_definitions() -> list[dict]:
    nodes = [
        ("design-management", "设计管理", None, 0, "[LOCAL_PATH_REDACTED]"),
        ("design-management/design-management-system", "设计管理体系", "design-management", 1, "[LOCAL_PATH_REDACTED]"),
        ("design-management/design-support", "设计支持", "design-management", 1, "[LOCAL_PATH_REDACTED]��.md"),
        ("design-management/epc-design-process", "EPC项目设计管理流程", "design-management", 1, "[LOCAL_PATH_REDACTED]��设计管理流程.md"),
        ("design-management/design-management-output", "设计管理成果总结", "design-management", 1, "[LOCAL_PATH_REDACTED]��结.md"),
    ]
    support = ("报批报建", "方案比选", "相关方沟通机制", "设计价值创造", "设计任务书", "设计策划", "设计计划", "设计评估", "设计质量", "设计风险", "限额设计", "设计招采")
    system = ("制度性文件", "工作计划", "管理指南")
    output = ("管理工具书", "管理经验交流", "设计复盘")
    for name in support:
        nodes.append((f"design-management/design-support/{name}", name, "design-management/design-support", 2, "[LOCAL_PATH_REDACTED]��.md"))
    nodes.extend([
        ("design-management/design-support/深化设计", "深化设计", "design-management/design-support", 2, "[LOCAL_PATH_REDACTED]��设计管理流程.md"),
        ("design-management/design-support/接口与提资", "接口与提资", "design-management/design-support", 2, "[LOCAL_PATH_REDACTED]��设计管理流程.md"),
    ])
    for name in (*system, "培训与能力建设"):
        nodes.append((f"design-management/design-management-system/{name}", name, "design-management/design-management-system", 2, "[LOCAL_PATH_REDACTED]"))
    for name in output:
        nodes.append((f"design-management/design-management-output/{name}", name, "design-management/design-management-output", 2, "[LOCAL_PATH_REDACTED]��结.md"))
    return [{"schema_version": "knowledge_os_v2_1.node", "node_id": node_id, "title": title, "parent_node_id": parent, "level": level, "knowledge_domain": "设计管理", "framework_status": "EXISTING_FRAMEWORK", "source": source} for node_id, title, parent, level, source in nodes]


RULES = {
    "design-management/design-support": ("设计支持", "raw/设计支持", "设计策划", "方案比选", "设计价值创造", "限额设计", "设计任务书", "设计评估", "设计质量", "设计风险", "报批报建"),
    "design-management/design-management-system": ("设计管理体系", "raw/设计管理体系", "制度性文件", "工作计划", "管理指南"),
    "design-management/design-management-system/培训与能力建设": ("培训与能力建设", "设计能力提升培训", "培训材料"),
    "design-management/design-management-output": ("设计管理成果总结", "项目经验总结库", "经验总结交流会", "管理经验交流", "设计复盘", "成果总结", "设计资源库", "资源库"),
    "design-management/epc-design-process": ("EPC", "工程总承包", "全生命周期", "项目设计管理流程"),
    "design-management/design-management-system": ("制度", "管理指南", "工作计划", "制度性文件"),
    "design-management/design-management-output": ("成果总结", "经验总结", "复盘", "案例", "管理工具书"),
    "design-management/design-support/报批报建": ("报批报建",),
    "design-management/design-support/方案比选": ("方案比选",),
    "design-management/design-support/相关方沟通机制": ("相关方沟通", "相关方沟通机制"),
    "design-management/design-support/设计价值创造": ("设计价值创造", "创效"),
    "design-management/design-support/设计任务书": ("设计任务书",),
    "design-management/design-support/设计策划": ("设计策划",),
    "design-management/design-support/设计计划": ("设计计划",),
    "design-management/design-support/设计评估": ("设计评估", "设计成果评审"),
    "design-management/design-support/设计质量": ("设计质量", "质量管控"),
    "design-management/design-support/设计风险": ("设计风险", "风险清单"),
    "design-management/design-support/限额设计": ("限额设计",),
    "design-management/design-support/设计招采": ("设计招采",),
    "design-management/design-support/深化设计": ("深化设计", "施工图深化", "深化"),
    "design-management/design-support/接口与提资": ("接口与提资", "接口管理", "提资", "接口清单"),
    "design-management/design-management-system/制度性文件": ("制度性文件",),
    "design-management/design-management-system/工作计划": ("工作计划",),
    "design-management/design-management-system/管理指南": ("管理指南",),
    "design-management/design-management-output/管理工具书": ("工具书", "指标库", "审核要点", "清单"),
    "design-management/design-management-output/管理经验交流": ("经验交流", "管理经验"),
    "design-management/design-management-output/设计复盘": ("设计复盘", "复盘总结"),
}


def classify(text: str, *, existing_node_ids: set[str] | None = None) -> list[dict]:
    value = text.casefold()
    bindings = [{"knowledge_node_id": "design-management", "method": "EXISTING_FRAMEWORK", "confidence": 1.0, "status": "VERIFIED"}]
    existing_node_ids = existing_node_ids or set()
    for node_id, terms in RULES.items():
        if node_id in existing_node_ids:
            bindings.append({"knowledge_node_id": node_id, "method": "EXISTING_FRAMEWORK", "confidence": 1.0, "status": "VERIFIED"})
        elif any(term.casefold() in value for term in terms):
            bindings.append({"knowledge_node_id": node_id, "method": "SECTION_HEADING_RULE", "confidence": 0.84, "status": "RULE_BASED"})
    dedup: dict[str, dict] = {}
    for binding in bindings:
        dedup.setdefault(binding["knowledge_node_id"], binding)
    return list(dedup.values())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    docs = read_jsonl(STAGING / "documents.jsonl")
    sections = read_jsonl(STAGING / "sections.jsonl")
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    definitions = node_definitions()
    definition_ids = {row["node_id"] for row in definitions}
    docs_by_id = {str(row.get("document_id")): row for row in docs}
    existing_doc_nodes = {str(row.get("document_id")): {"design-management"} for row in docs}
    for doc in docs:
        path = str(doc.get("source_path") or "").replace("/", "\\")
        if "\\wiki\\topics\\" in path.casefold():
            title = str(doc.get("title") or "")
            for row in definitions:
                if row["level"] == 1 and row["title"] in title:
                    existing_doc_nodes[str(doc.get("document_id"))].add(row["node_id"])
    bindings: list[dict] = []
    object_nodes: dict[tuple[str, str], dict] = {}
    detail_counts = Counter()
    for doc in docs:
        did = str(doc.get("document_id"))
        text = " ".join(str(doc.get(key) or "") for key in ("title", "file_name", "source_path"))
        chosen = classify(text, existing_node_ids=existing_doc_nodes.get(did))
        for binding in chosen:
            row = {"schema_version": "knowledge_os_v2_1.binding", "object_type": "DOCUMENT", "object_id": did, **binding}
            bindings.append(row); object_nodes[("DOCUMENT", did, binding["knowledge_node_id"])] = row
        detail_counts["DOCUMENT"] += bool(len(chosen) > 1)
    for section in sections:
        sid, did = str(section.get("section_id")), str(section.get("document_id"))
        doc = docs_by_id.get(did, {})
        text = " ".join(str(doc.get(key) or "") for key in ("title", "file_name", "source_path")) + " " + str(section.get("section_path") or "")
        chosen = classify(text)
        for binding in chosen:
            row = {"schema_version": "knowledge_os_v2_1.binding", "object_type": "SECTION", "object_id": sid, **binding}
            bindings.append(row); object_nodes[("SECTION", sid, binding["knowledge_node_id"])] = row
        detail_counts["SECTION"] += bool(len(chosen) > 1)
    for chunk in chunks:
        cid, did = str(chunk.get("chunk_id")), str(chunk.get("document_id"))
        doc = docs_by_id.get(did, {})
        text = " ".join(str(value or "") for value in (doc.get("title"), doc.get("file_name"), doc.get("source_path"), chunk.get("section_path"), chunk.get("raw_text")))
        chosen = classify(text)
        for binding in chosen:
            row = {"schema_version": "knowledge_os_v2_1.binding", "object_type": "SEMANTIC_CHUNK", "object_id": cid, **binding}
            bindings.append(row); object_nodes[("SEMANTIC_CHUNK", cid, binding["knowledge_node_id"])] = row
        detail_counts["SEMANTIC_CHUNK"] += bool(len(chosen) > 1)
    updates = []
    for chunk in chunks:
        cid = str(chunk.get("chunk_id"))
        node_ids = [key[2] for key in object_nodes if key[0] == "SEMANTIC_CHUNK" and key[1] == cid]
        updates.append({"schema_version": "knowledge_os_v2_1.chunk_node_update", "chunk_id": cid, "knowledge_node_ids": node_ids, "node_binding_method": "EXISTING_FRAMEWORK_PLUS_RULES", "node_binding_status": "VERIFIED" if any(row["method"] == "EXISTING_FRAMEWORK" and row["knowledge_node_id"] != "design-management" for row in [object_nodes[("SEMANTIC_CHUNK", cid, node)] for node in node_ids]) else "RULE_BASED", "root_only": len(node_ids) == 1})
    def write(name: str, rows: list[dict]) -> None:
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    write("node_definitions.jsonl", definitions)
    write("bindings.jsonl", bindings)
    write("chunk_node_updates.jsonl", updates)
    def coverage(kind: str, total: int) -> dict:
        ids = {row["object_id"] for row in bindings if row["object_type"] == kind}
        detailed = {row["object_id"] for row in bindings if row["object_type"] == kind and row["knowledge_node_id"] != "design-management"}
        return {"total": total, "any_node_bound": len(ids), "any_node_coverage": round(len(ids) / total, 4) if total else None, "detail_node_bound": len(detailed), "detail_node_coverage": round(len(detailed) / total, 4) if total else None, "root_only": total - len(detailed), "unbound": total - len(ids), "unbound_rate": round((total - len(ids)) / total, 4) if total else None}
    metrics = {"schema_version": "knowledge_os_v2_1.node_binding.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "node_count": len(definitions), "binding_count": len(bindings), "document": coverage("DOCUMENT", len(docs)), "section": coverage("SECTION", len(sections)), "semantic_chunk": coverage("SEMANTIC_CHUNK", len(chunks)), "verified_binding_rate": round(sum(row["status"] == "VERIFIED" for row in bindings) / len(bindings), 4) if bindings else None, "root_only_chunk_rate": round(sum(row["root_only"] for row in updates) / len(updates), 4) if updates else None, "rule_based_binding_count": sum(row["status"] == "RULE_BASED" for row in bindings), "proposed_binding_count": sum(row["status"] == "PROPOSED" for row in bindings), "unbound_chunk_target_pass": (sum(not row["root_only"] for row in updates) / len(updates) if updates else 0) >= 0.85}
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
