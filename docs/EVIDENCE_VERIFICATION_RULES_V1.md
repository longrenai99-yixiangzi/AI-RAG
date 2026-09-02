# EVIDENCE VERIFICATION RULES V1

1. Coverage before rank: each subquestion is independently COVERED, PARTIALLY_COVERED, CONFLICTED, NOT_COVERED or EVIDENCE_INSUFFICIENT.
2. Scope → fact relevance → role → authority → time → retrieval rank. Rank never resolves a fact conflict.
3. REGISTER_PAGE is excluded from direct facts; QUERY_PAGE is context-only when original source exists.
4. LINEAGE_PARTIAL blocks cross-source aggregation, not use of a single-source fact.
5. FILTER/COUNT structured facts require lineage-safe table evidence; otherwise EVIDENCE_INSUFFICIENT.
6. Same organization/year/metric with different numeric facts is CONFLICTING and retained.
