from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.knowledge_engineering.structured_v2 import build_structured_layer
from scripts.diagnose_v2_6_lost_hits import _find_target_pdf, _read_jsonl, _sha


ROOT = Path(__file__).resolve().parents[1]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    documents = _read_jsonl(ROOT / "data" / "shadow" / "knowledge_v2_5_staging" / "documents.jsonl")
    target = _find_target_pdf(documents)
    source_hash = _sha(target)
    source_id = "V261-" + hashlib.sha256(str(target.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
    builder = DocumentIntelligenceV2Builder(target.parents[3])
    raw_atomic = build_atomic_evidence(target, target.parents[3]).get("records") or []
    parsed = builder.build([target], raw_atomic)
    document = (parsed.get("documents") or [{}])[0]
    document.update({"source_id": source_id, "source_version": source_hash, "source_hash": source_hash, "effective_status": "PENDING_OWNER_APPROVAL"})
    registry = {str(target).casefold(): {"source_id": source_id, "source_path": str(target), "current_hash": source_hash, "body_status": "PENDING_OWNER_APPROVAL", "index_status": "DEV_REMEDIATION_ONLY"}}
    layer = build_structured_layer(parsed["documents"], parsed["sections"], parsed["paragraphs"], parsed["tables"], parsed["table_rows"], parsed["atomic_evidence"], registry)
    STAGING.mkdir(parents=True, exist_ok=True)
    for name in ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts", "atomic_evidence"):
        _write_jsonl(STAGING / f"{name}.jsonl", parsed.get(name) or [])
    _write_jsonl(STAGING / "semantic_chunks.jsonl", layer["semantic_chunks"])
    _write_jsonl(STAGING / "knowledge_node_bindings.jsonl", layer["knowledge_node_bindings"])
    hits = []
    for paragraph in parsed.get("paragraphs") or []:
        text = str(paragraph.get("text") or "")
        if any(term in text for term in ("\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a", "2035\u603b\u4f53\u884c\u52a8\u89c4\u5212", "\u4f9d\u62588\u4e2aBIM", "\u5149\u8c37\u5143\u8457")):
            hits.append({"text": text, "location": paragraph.get("location"), "evidence_id": paragraph.get("paragraph_id")})
    now = datetime.now(timezone.utc).astimezone().isoformat()
    manifest = {
        "schema_version": "knowledge_os_v2_6_1.dev_remediation_candidate",
        "candidate_id": "V2.6.1-DEV-LSR014",
        "captured_at": now,
        "status": "DEV_REMEDIATION_PENDING_OWNER_APPROVAL",
        "base_candidate_hash": json.loads((V25 / "candidate_v2_5_manifest.json").read_text(encoding="utf-8")).get("candidate_hash"),
        "repair_targets": ["LSR-014"],
        "source": {"source_id": source_id, "source_path": str(target), "file_name": target.name, "sha256": source_hash, "physical_exists": True, "parse_status": document.get("parse_status"), "effective_status": "PENDING_OWNER_APPROVAL", "index_status": "DEV_REMEDIATION_ONLY"},
        "parse_counts": {name: len(parsed.get(name) or []) for name in ("documents", "sections", "paragraphs", "tables", "table_rows", "atomic_evidence", "metadata_conflicts")},
        "semantic_chunks": {"count": len(layer["semantic_chunks"]), "path": str(STAGING / "semantic_chunks.jsonl")},
        "evidence_hits": hits,
        "embedding_status": "PENDING_NEW_CANDIDATE_EMBEDDING",
        "parameter_changes": False,
        "formal_8000_touched": False,
        "8010_switch_performed": False,
        "approval_note": "This sixth source is isolated for remediation only; it is not promoted into frozen V2.5 or formal indexes.",
    }
    (V26 / "remediation_candidate_v2_6_1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# V2.6.1 开发修复候选：LSR-014",
        "",
        "- 状态：`DEV_REMEDIATION_PENDING_OWNER_APPROVAL`",
        f"- 真实来源：`{target}`",
        f"- SHA-256：`{source_hash}`",
        f"- 解析：`{document.get('parse_status')}`；段落 `{len(parsed.get('paragraphs') or [])}`；原子证据 `{len(parsed.get('atomic_evidence') or [])}`；语义块 `{len(layer['semantic_chunks'])}`。",
        "- 边界：不改写冻结 V2.5，不写 8000，不切换 8010；新来源嵌入仍待候选审批后执行。",
        "",
        "## 已定位的 Q74 证据",
        "",
    ]
    for hit in hits:
        lines.append(f"- `{hit['location']}`：{hit['text']}")
    (ROOT / "docs" / "V2_6_1_REMEDIATION_CANDIDATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "source": target.name, "parse_status": document.get("parse_status"), "paragraphs": len(parsed.get("paragraphs") or []), "atomic_evidence": len(parsed.get("atomic_evidence") or []), "semantic_chunks": len(layer["semantic_chunks"]), "embedding_status": manifest["embedding_status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
