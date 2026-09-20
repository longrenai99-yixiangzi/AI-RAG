"""Write evidence-backed V2.1 phase and release reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V21 = ROOT / "evaluation" / "knowledge_os_v2_1"
DOCS = ROOT / "docs"


def read(name: str) -> dict:
    path = V21 / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    node = read("node_binding/metrics.json")
    chunk = read("chunk_governance/metrics.json")
    metadata = read("chunk_governance/metadata_metrics.json")
    gold = read("gold/gold_manifest.json")
    dense = read("retrieval_ab/dense_v2_metrics.json")
    lexical = read("retrieval_ab/lexical_matrix.json")
    l2 = ((lexical.get("versions") or {}).get("L2_section_title_path") or {}).get("metrics") or {}
    validator = read("validator/validator_v2_metrics.json")
    release = {"schema_version": "knowledge_os_v2_1.release_gate", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "recommendation": "REJECT", "gates": {"structure": "FAIL" if (node.get("semantic_chunk", {}).get("detail_node_coverage") or 0) < 0.85 else "PASS", "chunk_governance": "FAIL" if not chunk.get("quarantine_target_pass") else "PASS", "metadata": "FAIL", "retrieval_gold": "PASS" if gold.get("retrieval_gold_confirmed", 0) >= 50 else "FAIL", "retrieval_candidate": "FAIL" if dense.get("status") != "RUN" else "PENDING", "validator": "FAIL" if validator.get("status") != "RUN" else "PENDING", "regression": "NOT_RUN_BLOCKED", "holdout": "NOT_RUN_BLOCKED", "shadow": "NOT_RUN_BLOCKED", "rollback": "NOT_RUN_BLOCKED"}, "top_3_blocking_issues": ["Dense V2 未能在本机资源上完成：FlagEmbedding 导入 MemoryError；sentence-transformers 首个 batch 约 221 秒，已中止。", "Retrieval Gold 只有 10/50 道完成 Source/Section 人工确认，40 道仍 pending；不能用 provisional Gold 代替真值。", "Semantic Chunk 细分 Node 覆盖仅 56.70%，Quarantine 12.94%，结构门禁未通过。"], "runtime": {"8010_switch_allowed": False, "8000_touched": False, "v1_index_intact": True}}
    (V21 / "release_gate" / "release_gate.json").write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "KNOWLEDGE_GOVERNANCE_V2_1_REPORT.md").write_text(f"""# Knowledge Governance V2.1 Report\n\n- Documents: 518; Sections: 4,171; Semantic Chunks: 8,902\n- Node definitions: {node.get('node_count')}; Chunk any-node coverage: {node.get('semantic_chunk', {}).get('any_node_coverage')}; detail-node coverage: {node.get('semantic_chunk', {}).get('detail_node_coverage')}; root-only: {node.get('root_only_chunk_rate')}\n- Quarantine: {chunk.get('quarantined')} ({chunk.get('quarantine_rate')}); effective retrieval duplicate rate after suppression: {chunk.get('effective_duplicate_rate')}\n- Metadata: organization {metadata.get('document_fields', {}).get('organization', {}).get('fill_rate_all_documents')}; project {metadata.get('document_fields', {}).get('project', {}).get('fill_rate_all_documents')}; year {metadata.get('document_fields', {}).get('year', {}).get('fill_rate_all_documents')}; specialty {metadata.get('document_fields', {}).get('specialty', {}).get('fill_rate_all_documents')}; stage missing.\n\n结论：治理工件已建立，但细分节点覆盖和 Quarantine 未达到门禁；Metadata 当前均为 Inferred，未将其当作 Verified。\n""", encoding="utf-8")
    (DOCS / "RETRIEVAL_V2_FULL_AB_REPORT.md").write_text(f"""# Retrieval V2 Full A/B Report\n\nL1 Current BM25 V2: Recall@20 {((lexical.get('versions') or {}).get('L1_current_bm25_v2') or {}).get('metrics', {}).get('recall@20')}\n\nL2 Section Path/Title: Recall@5 {l2.get('recall@5')}, Recall@10 {l2.get('recall@10')}, Recall@20 {l2.get('recall@20')}, MRR {l2.get('mrr')}, nDCG@10 {l2.get('ndcg@10')}\n\nL3 Metadata/Node soft boost and L4 business dictionary were tested and did not improve over L2. Dense, Weighted Hybrid, RRF and Reranker are NOT_RUN because Dense V2 hit a local resource limit. Gold used here is provisional expected-file Gold (100 questions).\n""", encoding="utf-8")
    (DOCS / "RETRIEVAL_GOLD_AND_VALIDATOR_REPORT.md").write_text(f"""# Retrieval Gold and Validator Report\n\n- Retrieval Gold package: 50 records; confirmed {gold.get('retrieval_gold_confirmed')}; pending {gold.get('retrieval_gold_pending')}.\n- Answer Gold confirmed: {gold.get('answer_gold_confirmed')}; target 30.\n- Existing V1 validator baseline remains provisional: Evidence False Reject 30.23% (13/43).\n- V2 candidate validator: NOT_RUN because Dense/Hybrid candidate is unavailable.\n\n不得把 pending Gold 或旧 provisional validator 结果写成 V2 Gate 通过。\n""", encoding="utf-8")
    (DOCS / "REGRESSION_HOLDOUT_SHADOW_REPORT.md").write_text("""# Regression / Holdout / Shadow Report\n\nRegression 48、Holdout 30、Shadow Retrieval 和 Rollback 尚未运行。原因是 V2 Candidate 尚未冻结：Dense V2 未完成，Retrieval Gold 只有 10/50 confirmed，Structure/Chunk Gate 也未通过。Holdout 原有基线未修改。\n""", encoding="utf-8")
    (DOCS / "RETRIEVAL_V2_RELEASE_GATE.md").write_text("""# Retrieval V2 Release Gate\n\n## Recommendation\n\n`REJECT`\n\n## Top 3 Blocking Issues\n\n1. Dense V2 未完成：本机 CPU 资源不足，未生成向量。\n2. Retrieval Gold 只有 10/50 道完成 Source/Section 人工确认。\n3. Semantic Chunk 细分 Node 覆盖 56.70%，Quarantine 12.94%，未达到门禁。\n\n8010 不得切换；8000 全程未触碰。\n""", encoding="utf-8")
    (DOCS / "KNOWLEDGE_OS_V2_1_FINAL_REPORT.md").write_text(json.dumps({"current_status": release, "node": node, "chunk": chunk, "metadata": metadata, "gold": gold, "dense": dense, "lexical": lexical}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(release, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
