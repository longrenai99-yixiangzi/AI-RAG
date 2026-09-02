from app.verified_answer_engine_v2 import render, validate


def test_verified_answer_has_direct_claim_and_citation():
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}]))
    assert answer["answer_status"] == "ANSWERED"
    assert answer["validation_status"] == "VALID"
    assert answer["claims"][0]["citation_ids"]


def test_verified_answer_uses_source_local_window_not_chunk_prefix():
    text = "\u524d\u7f6e\u76ee\u5f55\u548c\u8bf4\u660e\u3002\n\u8bbe\u8ba1\u4efb\u52a1\u4e66\u5e94\u5305\u542b\u8bbe\u8ba1\u8303\u56f4\u3001\u6210\u679c\u8981\u6c42\u548c\u8ba1\u5212\u8282\u70b9\u3002\n\u540e\u7eed\u8bf4\u660e\u3002"
    question = "\u8bbe\u8ba1\u4efb\u52a1\u4e66\u9700\u8981\u5305\u542b\u54ea\u4e9b\u5185\u5bb9\uff1f"
    evidence = _evidence("DIRECT", text=text)
    answer = render(_bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "\u8bbe\u8ba1\u8303\u56f4\u3001\u6210\u679c\u8981\u6c42\u548c\u8ba1\u5212\u8282\u70b9" in answer["answer_text"]
    assert "\u524d\u7f6e\u76ee\u5f55" not in answer["answer_text"]


def test_verified_answer_prefers_direct_evidence_with_the_best_local_match():
    question = "\u8bbe\u8ba1\u4efb\u52a1\u4e66\u9700\u8981\u5305\u542b\u54ea\u4e9b\u5185\u5bb9\uff1f"
    broad = _evidence("DIRECT", text="\u8bbe\u8ba1\u4efb\u52a1\u4e66\u7ba1\u7406\u3002", location={"line_start": 1})
    specific = {**_evidence("DIRECT", text="\u8bbe\u8ba1\u4efb\u52a1\u4e66\u5305\u542b\u9879\u76ee\u6982\u51b5\u3001\u5de5\u4f5c\u8303\u56f4\u3001\u5de5\u4f5c\u8981\u6c42\u548c\u8bbe\u8ba1\u6280\u672f\u8981\u70b9\u3002", location={"line_start": 2}), "evidence_id": "E2", "candidate_rank": 2}
    answer = render(_bundle("VERIFIED", [broad, specific], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert answer["claims"][0]["evidence_ids"] == ["E2"]


def test_content_question_prefers_a_direct_content_statement():
    question = "\u8bbe\u8ba1\u4efb\u52a1\u4e66\u9700\u8981\u5305\u542b\u54ea\u4e9b\u5185\u5bb9\uff1f"
    broad = _evidence("DIRECT", text="\u8bbe\u8ba1\u4efb\u52a1\u4e66\u7ba1\u7406\u6d41\u7a0b\u3002")
    content = {**_evidence("DIRECT", text="\u8bbe\u8ba1\u4efb\u52a1\u4e66\u5305\u542b\u9879\u76ee\u6982\u51b5\u3001\u5de5\u4f5c\u8303\u56f4\u548c\u5de5\u4f5c\u8981\u6c42\u3002"), "evidence_id": "E2", "candidate_rank": 2}
    answer = render(_bundle("VERIFIED", [broad, content], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert answer["claims"][0]["evidence_ids"] == ["E2"]


def test_verified_answer_uses_the_best_repeated_local_anchor():
    question = "\u8bbe\u8ba1\u4efb\u52a1\u4e66\u9700\u8981\u5305\u542b\u54ea\u4e9b\u5185\u5bb9\uff1f"
    text = "\u8bbe\u8ba1\u4efb\u52a1\u4e66\u7ba1\u7406\u3002\n\u8bbe\u8ba1\u4efb\u52a1\u4e66\u5e94\u5305\u542b\u8bbe\u8ba1\u8303\u56f4\u548c\u6210\u679c\u8981\u6c42\u3002"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "\u5305\u542b\u8bbe\u8ba1\u8303\u56f4\u548c\u6210\u679c\u8981\u6c42" in answer["answer_text"]


def test_structured_question_renders_conclusion_instead_of_raw_evidence_dump():
    question = "\u8bbe\u8ba1\u8bc4\u4f30\u8981\u8bc4\u4f30\u8bbe\u8ba1\u6587\u4ef6\u7684\u54ea\u4e9b\u65b9\u9762\uff1f"
    text = "3 \u8bbe\u8ba1\u8bc4\u4f30 3.1 \u8bbe\u8ba1\u5b8c\u6574\u5ea6\u8bc4\u4f30\u7ecf\u8fc7\u5bf9\u57fa\u7840\u8d44\u6599\u3001\u6307\u6807\u3001\u56fe\u7eb8\u3001\u8ba1\u7b97\u4e66\u7b49\u6587\u4ef6\u8fdb\u884c\u8bc4\u4f30\u3002 3.2 \u8bbe\u8ba1\u6df1\u5ea6\u8bc4\u4f30\u5bf9\u8bbe\u8ba1\u6587\u4ef6\u7684\u6df1\u5ea6\u8fdb\u884c\u8bc4\u4f30\u3002"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "\u7ed3\u8bba\uff1a\u8bbe\u8ba1\u8bc4\u4f30\u4e3b\u8981\u5305\u62ec\u8bbe\u8ba1\u5b8c\u6574\u5ea6\u8bc4\u4f30\u3001\u8bbe\u8ba1\u6df1\u5ea6\u8bc4\u4f30" in answer["answer_text"]
    assert "\u57fa\u7840\u8d44\u6599\u3001\u6307\u6807\u3001\u56fe\u7eb8\u3001\u8ba1\u7b97\u4e66" not in answer["answer_text"]


def test_chinese_and_bullet_headings_render_as_labels_not_source_paragraphs():
    question = "\u8bbe\u8ba1\u8bc4\u4f30\u5305\u62ec\u54ea\u4e9b\u5185\u5bb9\uff1f"
    text = "\u4e00\u3001\u5b8c\u6574\u6027\uff1a\u6838\u67e5\u57fa\u7840\u8d44\u6599\u3001\u56fe\u7eb8\u548c\u8ba1\u7b97\u4e66\u3002 \uff08\u4e8c\uff09\u6df1\u5ea6\uff1a\u6838\u67e5\u8bbe\u8ba1\u6587\u4ef6\u7684\u8868\u8fbe\u6df1\u5ea6\u3002 - \u534f\u540c\u6027\uff1a\u6838\u67e5\u4e13\u4e1a\u63a5\u53e3\u3002"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "\u7ed3\u8bba\uff1a\u8bbe\u8ba1\u8bc4\u4f30\u4e3b\u8981\u5305\u62ec\u5b8c\u6574\u6027\u3001\u6df1\u5ea6\u3001\u534f\u540c\u6027" in answer["answer_text"]
    assert "\u57fa\u7840\u8d44\u6599\u3001\u56fe\u7eb8\u548c\u8ba1\u7b97\u4e66" not in answer["answer_text"]


def test_same_document_consecutive_sections_are_merged_into_one_conclusion():
    question = "\u8bbe\u8ba1\u8bc4\u4f30\u8981\u8bc4\u4f30\u8bbe\u8ba1\u6587\u4ef6\u7684\u54ea\u4e9b\u65b9\u9762\uff1f"
    first = _evidence("DIRECT", text="3.1 \u8bbe\u8ba1\u5b8c\u6574\u5ea6\u8bc4\u4f30\u3002 3.2 \u8bbe\u8ba1\u6df1\u5ea6\u8bc4\u4f30\u3002", location={"page": 40})
    second = {**_evidence("DIRECT", text="3.3 \u6280\u672f\u53ef\u884c\u6027\u8bc4\u4f30\u3002", location={"page": 41}), "evidence_id": "E2", "candidate_rank": 2}
    answer = render(_bundle("VERIFIED", [first, second], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "\u7ed3\u8bba\uff1a\u8bbe\u8ba1\u8bc4\u4f30\u4e3b\u8981\u5305\u62ec\u8bbe\u8ba1\u5b8c\u6574\u5ea6\u8bc4\u4f30\u3001\u8bbe\u8ba1\u6df1\u5ea6\u8bc4\u4f30\u3001\u6280\u672f\u53ef\u884c\u6027\u8bc4\u4f30" in answer["answer_text"]
    assert answer["claims"][0]["evidence_ids"] == ["E1", "E2"]
    assert len(answer["citations"]) == 2


def test_exact_core_phrase_evidence_beats_a_topic_adjacent_candidate():
    question = "二级设计进度计划，包含哪些节点？"
    adjacent = _evidence("DIRECT", text="3.2 设计进度要求。 3.3 设计限额要求。")
    exact = {**_evidence("DIRECT", text="二级设计进度计划：应包括初步设计\n完成、基坑支护设计完成和专项外部审查完成等节点。\n三级设计进度计划：由二级设计进度计划分解制定。"), "evidence_id": "E2", "candidate_rank": 2, "exact_core_phrase_matches": ["二级设计进度计划"]}
    answer = render(_bundle("VERIFIED", [adjacent, exact], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "初步设计完成" in answer["answer_text"]
    assert "初步设计 完成" not in answer["answer_text"]
    assert "三级设计进度计划" not in answer["answer_text"]
    assert answer["claims"][0]["evidence_ids"] == ["E2"]


def test_role_question_prefers_the_evidence_that_states_organizer_and_participants():
    question = "阶段性设计成果审查是由谁组织，谁参与？"
    broad = _evidence("DIRECT", text="项目部参与阶段性设计成果审查等设计支持工作。")
    exact = {**_evidence("DIRECT", text="阶段性设计成果审查 1）阶段性设计成果审查由设计支持机构牵头，项目部参与，设计支持机构负责把关。"), "evidence_id": "E2", "candidate_rank": 6}
    answer = render(_bundle("VERIFIED", [broad, exact], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "设计支持机构牵头" in answer["answer_text"]
    assert "项目部参与" in answer["answer_text"]
    assert "审查1）" not in answer["answer_text"]
    assert "审查阶段性设计成果审查" not in answer["answer_text"]
    assert answer["claims"][0]["evidence_ids"] == ["E2"]


def test_risk_response_table_renders_rows_instead_of_only_the_header():
    question = "设计风险应对措施有哪些？"
    text = "表13-2 设计风险应对措施\n编号\n风险描述\n应对策略\n应对措施\n1\n设计文件不满足报批报建进度要求风险\n风险规避、风险化解\n1）了解报批报建流程；2）审查设计计划。\n2\n设计条件不充分的风险\n风险规避、风险化解\n1）协助设计单位落实设计条件。"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "设计文件不满足报批报建进度要求风险" in answer["answer_text"]
    assert "了解报批报建流程" in answer["answer_text"]
    assert "设计条件不充分的风险" in answer["answer_text"]


def test_partial_answer_keeps_uncovered_subquestion_as_limitation():
    answer = render(_bundle("VERIFIED_PARTIAL", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "EVIDENCE_INSUFFICIENT", "subquestion": "条件统计"}]))
    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert any(claim["claim_type"] == "INSUFFICIENT" for claim in answer["claims"])


def test_conflict_bundle_cannot_silently_resolve():
    evidence = _evidence("CONFLICTING")
    answer = render(_bundle("CONFLICTING_EVIDENCE", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "CONFLICTED"}]))
    assert answer["answer_status"] == "CONFLICTING_ANSWER"
    assert answer["answer_text"].startswith("结论：当前可核查资料")
    assert answer["claims"][0]["claim_type"] == "LIMITATION"
    assert validate(answer, _bundle("CONFLICTING_EVIDENCE", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "CONFLICTED"}]))["valid"]


def test_conflict_renderer_merges_identical_metric_claims():
    text = "\u8bbe\u8ba1\u521b\u6548\u91d1\u989d6.9\u4ebf\u5143"
    first = _evidence("CONFLICTING", text=text)
    second = {**_evidence("CONFLICTING", text=text), "evidence_id": "E2"}
    answer = render(_bundle("CONFLICTING_EVIDENCE", [first, second], [{"subquestion_id": "SQ1", "coverage_status": "CONFLICTED"}]))
    assert len(answer["claims"]) == 2
    assert answer["claims"][1]["evidence_ids"] == ["E1", "E2"]


def test_scope_missing_has_no_business_claim():
    answer = render(_bundle("SOURCE_SCOPE_MISSING", [], [{"subquestion_id": "SQ1", "coverage_status": "NOT_COVERED"}]))
    assert answer["answer_status"] == "SOURCE_SCOPE_MISSING"
    assert not answer["claims"]
    assert answer["answer_text"].startswith("结论：")


def test_direct_claim_rejects_supporting_evidence():
    bundle = _bundle("VERIFIED", [_evidence("SUPPORTING")], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}])
    answer = render(bundle)
    answer["claims"] = [{"claim_id": "C1", "claim_type": "DIRECT", "subquestion_id": "SQ1", "evidence_ids": ["E1"], "citation_ids": ["S1"]}]
    answer["citations"] = [{"citation_id": "S1", "evidence_id": "E1"}]
    assert not validate(answer, bundle)["valid"]


def test_citation_must_bind_same_evidence():
    bundle = _bundle("VERIFIED", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}])
    answer = render(bundle)
    answer["claims"][0]["citation_ids"] = ["S999"]
    assert not validate(answer, bundle)["valid"]


def test_structured_table_answer_uses_table_counts():
    evidence = _evidence("DIRECT", text="建筑 | A\n建筑 | B\n结构 | C", location={"table": 1, "rows": 3})
    bundle = _bundle("VERIFIED_PARTIAL", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY")
    answer = render(bundle)
    assert answer["answer_text"].startswith("结论：")
    assert "建筑2条" in answer["answer_text"]


def test_partial_validator_blocks_direct_claim_for_insufficient_subquestion():
    bundle = _bundle("VERIFIED_PARTIAL", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "EVIDENCE_INSUFFICIENT"}])
    answer = render(bundle)
    answer["claims"] = [{"claim_id": "C1", "claim_type": "DIRECT", "subquestion_id": "SQ1", "evidence_ids": ["E1"], "citation_ids": ["S1"]}]
    answer["citations"] = [{"citation_id": "S1", "evidence_id": "E1"}]
    assert not validate(answer, bundle)["valid"]


def _bundle(status, evidence, coverage, query_type="SOURCE_LOOKUP", question="测试问题"):
    return {"query_id": "Q", "question": question, "query_plan": {"query_type": query_type, "aggregation_plan": []}, "bundle_status": status, "candidate_evidence": evidence, "verified_evidence": evidence if status != "CONFLICTING_EVIDENCE" else [], "supporting_evidence": [], "conflicting_evidence": evidence if status == "CONFLICTING_EVIDENCE" else [], "excluded_evidence": [], "coverage_map": coverage, "conflict_map": {}, "structured_fact_map": {}}


def _evidence(role, text="已核查的直接事实", location=None):
    return {"evidence_id": "E1", "role": role, "text": text, "candidate_rank": 1, "document_id": "D1", "source_path": "D:/source.md", "file_name": "source.md", "heading_path": "章节", "location": location or {"line_start": 1, "line_end": 1}}
