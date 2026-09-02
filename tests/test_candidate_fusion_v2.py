from app.retrieval.candidate_fusion_v2 import apply_reranker_scores, final_evidence, fuse_evidence_candidates
from app.retrieval.query_planner_v1 import plan_query


def test_fusion_keeps_scope_above_wrong_scope_authority_and_deduplicates():
    plan = plan_query("2026年星谷科创中心项目设计价值创造清单有多少条？")
    result = {
        "document_candidates": [
            _document("target", "L4", {"project": ["星谷科创中心项目"], "year": ["2026"]}, rank=2),
            _document("wrong", "L1", {"project": ["其他项目"], "year": ["2026"]}, rank=1),
        ],
        "section_candidates": [_section("s-target", "target", 2), _section("s-wrong", "wrong", 1)],
        "table_candidates": [],
        "atomic_candidates": [
            _evidence("e-target", "target", "s-target", 2),
            _evidence("e-wrong", "wrong", "s-wrong", 1),
            _evidence("e-target", "target", "s-target", 3),
        ],
    }
    atomic = {row["evidence_id"]: row for row in result["atomic_candidates"]}
    rows = fuse_evidence_candidates(plan=plan, result=result, atomic_by_id=atomic, evidence_dense_scores={"e-target": 0.9, "e-wrong": 0.8})
    assert len(rows) == 2
    assert rows[0]["evidence_id"] == "e-target"
    assert rows[0]["scope_match"] == "MATCH"
    assert rows[1]["scope_match"] == "PARTIAL"
    reranked = apply_reranker_scores(rows, [0.2, 0.9])
    selected = final_evidence(reranked, limit=2)
    assert {row["evidence_id"] for row in selected} == {"e-target", "e-wrong"}


def _document(document_id, authority, scope, rank):
    return {"document_id": document_id, "rank": rank, "bm25_rank": rank, "dense_rank": rank, "rrf_score": 0.02, "authority": authority, "scope": scope, "document_type": "PROJECT_PLAN", "source_path": f"D:/{document_id}.xlsx", "metadata_match": [], "planner_match": {}}


def _section(section_id, document_id, rank):
    return {"section_id": section_id, "document_id": document_id, "rank": rank, "bm25_rank": rank, "dense_rank": rank, "rrf_score": 0.02, "source_path": f"D:/{document_id}.xlsx", "metadata_match": [], "planner_match": {}}


def _evidence(evidence_id, document_id, section_id, rank):
    return {"evidence_id": evidence_id, "document_id": document_id, "section_id": section_id, "rank": rank, "source_path": f"D:/{document_id}.xlsx", "file_name": f"{document_id}.xlsx", "text": "value creation rows", "location": {"sheet_name": "Sheet1"}, "candidate_origin": "HIERARCHICAL", "lineage_status": "LINEAGE_NOT_APPLICABLE"}
