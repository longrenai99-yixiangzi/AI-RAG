from app.verified_answer_engine_v2 import _narrative_count_document_score, render, validate


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


def test_xlsx_field_question_prefers_the_approved_workbook_over_adjacent_docx():
    question = "学校类产品线设计指标中，电气专业设计参数，包含哪些"
    workbook = _evidence(
        "DIRECT",
        text=(
            "第3行：列54：电气专业设计参数 | 列66：景观专业设计参数\n"
            "第4行：列54：市政电源引入路数 | 列55：自备电源路数 | "
            "列56：自备电源类型 | 列57：最高用电负荷等级"
        ),
    )
    workbook.update({"evidence_id": "XLSX", "file_name": "产品线设计指标库（学校）.xlsx", "source_path": "[LOCAL_PATH_REDACTED]"})
    workbook_context = _evidence("SUPPORTING", text="第3行：列54：电气专业设计参数 | 列66：景观专业设计参数")
    workbook_context.update({"evidence_id": "XLSX-CONTEXT", "file_name": "产品线设计指标库（学校）.xlsx", "source_path": "[LOCAL_PATH_REDACTED]"})
    adjacent = _evidence("DIRECT", text="智能化包含视频安防监控、电梯五方对讲。")
    adjacent.update({"evidence_id": "DOCX", "file_name": "光谷实验中学.docx", "source_path": "[LOCAL_PATH_REDACTED]"})
    bundle = _bundle("VERIFIED", [workbook, workbook_context, adjacent], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question)
    answer = render(bundle)
    assert "电气专业设计参数包括：市政电源引入路数、自备电源路数、自备电源类型、最高用电负荷等级" in answer["answer_text"]
    assert answer["citations"][0]["source_path"] == "[LOCAL_PATH_REDACTED]"


def test_pdf_value_creation_question_counts_professions_from_summary_page():
    question = "设计价值创造点清单里，包含了多少个专业"
    evidence = _evidence(
        "DIRECT",
        text=(
            "设计价值创造点各专业、阶段数量统计\n专业\n阶段\n方案设计\n初步设计\n施工图设计\n备注\n"
            "总图规划\n9\n0\n2\n建筑\n8\n3\n48\n电气\n2\n5\n38\n合计\n88\n72\n578"
        ),
    )
    evidence.update({"file_name": "设计价值创造点清单20260903.pdf", "source_path": "[LOCAL_PATH_REDACTED]��创造点清单.pdf", "location": {"page": 3}})
    answer = render(_bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question, query_type="AGGREGATION_QUERY"))
    assert answer["answer_status"] == "ANSWERED"
    assert "3个专业" in answer["answer_text"]
    assert answer["citations"][0]["location"] == {"page": 3}


def test_pdf_value_creation_stage_question_is_not_taken_by_profession_count_rule():
    question = "设计价值创造点清单中，各专业、阶段数量统计的方案设计、初步设计、施工图设计和合计分别是多少条？"
    evidence = _evidence(
        "DIRECT",
        text=(
            "设计价值创造点各专业、阶段数量统计\n专业\n阶段\n方案设计\n初步设计\n施工图设计\n备注\n"
            "总图规划\n9\n0\n2\n建筑\n8\n3\n48\n合计\n88\n72\n578"
        ),
    )
    evidence.update({"file_name": "设计价值创造点清单20260903.pdf", "location": {"page": 3}})
    answer = render(_bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question, query_type="AGGREGATION_QUERY"))
    assert "方案设计：88条" in answer["answer_text"]
    assert "总图规划：11条" not in answer["answer_text"]


def test_review_point_question_renders_at_least_five_points_from_approved_xlsx_section():
    question = "图纸审查中，电气专业的动力及照明配电系统的审查要点有哪些，说出不少于5条"
    review = _evidence(
        "DIRECT",
        text=(
            "工作表：全专业施工图审核要点提示汇编正文\n动力及照明配电系统\n"
            "3.1由变电所供电的住宅宜采用TN系统。\n"
            "3.3设备间、竖井面积合理。\n"
            "3.4暗装配电箱位置合理。\n"
            "3.6与其它系统联动关系明确。\n"
            "3.7配电系统图应标注详细。"
        ),
    )
    review.update({"evidence_id": "REVIEW-XLSX", "file_name": "全专业施工图审核要点提示汇编（2026年）.xlsx", "source_path": "[LOCAL_PATH_REDACTED]�点.xlsx"})
    adjacent = _evidence("DIRECT", text="电气专业有3条风险。")
    adjacent.update({"evidence_id": "RISK-DOCX", "file_name": "能源环保风险清单.docx", "source_path": "[LOCAL_PATH_REDACTED]"})
    bundle = _bundle("VERIFIED", [review, adjacent], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question)
    answer = render(bundle)
    assert "3.1由变电所供电的住宅宜采用TN系统" in answer["answer_text"]
    assert "3.7配电系统图应标注详细" in answer["answer_text"]
    assert answer["citations"][0]["source_path"] == "[LOCAL_PATH_REDACTED]�点.xlsx"


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
    bundle = _bundle("VERIFIED_PARTIAL", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY", question="各专业分别有多少条？")
    answer = render(bundle)
    assert answer["answer_text"].startswith("结论：")
    assert "建筑2条" in answer["answer_text"]


def test_partial_validator_blocks_direct_claim_for_insufficient_subquestion():
    bundle = _bundle("VERIFIED_PARTIAL", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "EVIDENCE_INSUFFICIENT"}])
    answer = render(bundle)
    answer["claims"] = [{"claim_id": "C1", "claim_type": "DIRECT", "subquestion_id": "SQ1", "evidence_ids": ["E1"], "citation_ids": ["S1"]}]
    answer["citations"] = [{"citation_id": "S1", "evidence_id": "E1"}]
    assert not validate(answer, bundle)["valid"]


def test_organization_structure_keeps_common_and_optional_boundaries():
    question = "中建三局二公司设计与技术支持中心的组织架构是什么样的"
    text = (
        "由公司设计与技术管理部统筹全司设计与技术支持工作，公司总部设置设计与技术支持中心，作为公司设计与技术管理部二级部室。"
        "司属各分公司（事业部）均设置设计与技术支持中心，作为各分公司（事业部）设计与技术管理部二级部室。"
        "各分公司（事业部）设计与技术支持中心均设置设计支持岗、深化设计岗、方案支持岗。"
        "区域分公司中心选择设置技术投标岗、钢筋翻样岗，专业公司中心选择设置技术投标岗。"
    )
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [
        {"subquestion_id": "SQ1", "coverage_status": "COVERED"},
        {"subquestion_id": "SQ2", "coverage_status": "COVERED"},
        {"subquestion_id": "SQ3", "coverage_status": "COVERED"},
    ], question=question))
    assert answer["answer_status"] == "ANSWERED"
    assert "均设置设计支持岗、深化设计岗、方案支持岗" in answer["answer_text"]
    assert "区域分公司中心选择设置技术投标岗、钢筋翻样岗" in answer["answer_text"]
    assert "专业公司中心选择设置技术投标岗" in answer["answer_text"]


def test_organization_boundary_question_does_not_turn_optional_into_required():
    question = "专业公司中心必须设钢筋翻样岗吗？"
    text = "各分公司中心均设置设计支持岗、深化设计岗、方案支持岗。区域分公司中心选择设置技术投标岗、钢筋翻样岗，专业公司中心选择设置技术投标岗。"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "不能认定专业公司中心必须设置钢筋翻样岗" in answer["answer_text"]


def test_all_branches_boundary_question_is_corrected():
    question = "所有分公司都必须设置钢筋翻样岗吗？"
    text = "各分公司（事业部）设计与技术支持中心均设置设计支持岗、深化设计岗、方案支持岗。区域分公司中心选择设置技术投标岗、钢筋翻样岗，专业公司中心选择设置技术投标岗。"
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT", text=text)], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "该说法不准确" in answer["answer_text"]
    assert "选择设置" in answer["answer_text"]


def test_organization_alias_answer_is_labeled_as_search_configuration():
    question = "中建三局第二建设公司设计与技术支持中心与二公司设计与技术支持中心是什么关系？"
    evidence = _evidence("DIRECT", text="中建三局第二建设公司：中建三局二公司,第二建设公司,二公司")
    evidence.update({"source_id": "SYS_ORGANIZATION_ALIASES", "file_name": "组织别名配置（系统）", "location": {"config_key": "ORGANIZATION_ALIASES"}})
    answer = render(_bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "归一为同一组织称谓" in answer["answer_text"]
    assert "只用于查询和范围识别" in answer["answer_text"]


def test_reviewed_standard_answer_beats_unrelated_high_relevance_evidence():
    question = "各经营实体的设计技术支持团队是什么管理层级？"
    wrong = _evidence("DIRECT", text="设计与技术支持团队开展服务品质比拼。")
    reviewed = _evidence("DIRECT", text="司属各分公司（事业部）的设计与技术支持中心作为设计与技术管理部二级部室。")
    reviewed.update({"evidence_id": "K1", "approved_trial_knowledge": True, "knowledge_id": "KN1", "search_context": question, "candidate_rank": 2})
    answer = render(_bundle("VERIFIED", [wrong, reviewed], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "二级部室" in answer["answer_text"]
    assert answer["citations"][0]["evidence_id"] == "K1"


def test_other_organization_relationship_is_rendered_from_its_own_evidence():
    question = "华东公司设计中心隶属哪个部门？"
    evidence = _evidence("DIRECT", text="华东公司设计中心作为华东公司技术质量部二级部室。")
    answer = render(_bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert "华东公司技术质量部二级部室" in answer["answer_text"]
    assert "中建三局第二建设公司" not in answer["answer_text"]


def test_generic_planning_list_prefers_explicit_top_ranked_sentence():
    question = "设计管理策划包括哪些核心清单？"
    correct = _evidence("DIRECT", text="开展设计管理策划工作，形成设计合约规划、方案比选、设计风险识别、设计价值创造等核心任务清单。")
    wrong = _evidence("DIRECT", text="3.1 总体管理 3.2 核心业务管理 3.3 监督与检查")
    wrong.update({"evidence_id": "E2", "candidate_rank": 2})
    answer = render(_bundle("VERIFIED", [correct, wrong], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="STRUCTURED_QUERY", question=question))
    assert all(term in answer["answer_text"] for term in ("设计合约规划", "方案比选", "设计风险识别", "设计价值创造"))


def test_generic_evaluation_aspects_do_not_turn_an_unrelated_table_into_counts():
    question = "设计评估报告通常应包括哪些方面？"
    correct = _evidence("DIRECT", text="设计评估包括设计完整性、设计深度、技术可行性评估。")
    table = _evidence("DIRECT", text="建筑 | A", location={"table": 1, "rows": 1})
    table.update({"evidence_id": "E2", "candidate_rank": 2})
    answer = render(_bundle("VERIFIED", [correct, table], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="STRUCTURED_QUERY", question=question))
    assert all(term in answer["answer_text"] for term in ("设计完整性", "设计深度", "技术可行性"))
    assert "建筑1条" not in answer["answer_text"]


def test_narrative_project_count_uses_the_best_direct_source_sentence():
    question = "2025年度多少个项目成功打造为设计管理示范项目？"
    summary = _evidence("DIRECT", text="二是打造设计管理示范项目。通过设计赋能，成功打造4个设计增效7%以上的标杆项目。")
    exact = _evidence("DIRECT", text="发布设计管理示范项目打造方案，最终4个项目成功打造为设计管理示范项目，设计效益增量达7%以上。")
    exact.update({"evidence_id": "E2", "candidate_rank": 2})
    bundle = _bundle("VERIFIED", [summary, exact], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY", question=question)
    bundle["query_plan"]["aggregation_plan"] = ["COUNT"]
    answer = render(bundle)
    assert answer["answer_status"] == "ANSWERED"
    assert "最终4个项目成功打造为设计管理示范项目" in answer["answer_text"]
    assert answer["citations"][0]["evidence_id"] == "E2"


def test_narrative_project_count_accepts_rephrasing_and_rejects_another_demo_domain():
    question = "2025年有几个项目完成了设计管理示范项目打造？"
    correct = _evidence("DIRECT", text="最终4个项目成功打造为设计管理示范项目。")
    wrong = _evidence("DIRECT", text="成功打造1项省级智能建造试点企业、9个智能建造试点示范项目。")
    wrong.update({"evidence_id": "E2", "candidate_rank": 1})
    correct["candidate_rank"] = 2
    bundle = _bundle("VERIFIED", [wrong, correct], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY", question=question)
    bundle["query_plan"]["aggregation_plan"] = ["COUNT"]
    answer = render(bundle)
    assert "最终4个项目成功打造为设计管理示范项目" in answer["answer_text"]
    assert answer["citations"][0]["evidence_id"] == "E1"
    unrelated = "前文提到设计管理示范项目。另举办观摩会，成功打造9个智能建造试点示范项目。"
    assert _narrative_count_document_score(unrelated, question) == 0


def test_inventory_register_multi_fact_claim_keeps_all_counts_in_one_source_window():
    question = "设计支持中心资料登记共登记多少份资料？其中设计策划和责任状各多少份？"
    first = _evidence("DIRECT", text="登记设计管理资料（共 1110 份）。")
    second = {**_evidence("DIRECT", text="设计策划：76；责任状：337"), "evidence_id": "E2", "source_id": "SAME-SOURCE"}
    first["source_id"] = "SAME-SOURCE"
    bundle = _bundle(
        "VERIFIED",
        [first, second],
        [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}],
        query_type="AGGREGATION_QUERY",
        question=question,
    )
    bundle["query_plan"]["aggregation_plan"] = ["COUNT", "FILTER", "GROUP_BY"]
    answer = render(bundle)
    assert answer["answer_status"] == "ANSWERED"
    assert "1110" in answer["answer_text"] and "76" in answer["answer_text"] and "337" in answer["answer_text"]


def _bundle(status, evidence, coverage, query_type="SOURCE_LOOKUP", question="测试问题"):
    return {"query_id": "Q", "question": question, "query_plan": {"query_type": query_type, "aggregation_plan": []}, "bundle_status": status, "candidate_evidence": evidence, "verified_evidence": evidence if status != "CONFLICTING_EVIDENCE" else [], "supporting_evidence": [], "conflicting_evidence": evidence if status == "CONFLICTING_EVIDENCE" else [], "excluded_evidence": [], "coverage_map": coverage, "conflict_map": {}, "structured_fact_map": {}}


def _evidence(role, text="已核查的直接事实", location=None):
    return {"evidence_id": "E1", "role": role, "text": text, "candidate_rank": 1, "document_id": "D1", "source_path": "[LOCAL_PATH_REDACTED]", "file_name": "source.md", "heading_path": "章节", "location": location or {"line_start": 1, "line_end": 1}}
