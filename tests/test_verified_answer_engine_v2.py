from app.verified_answer_engine_v2 import _answer, _claim, _narrative_count_document_score, render, validate
from app.retrieval.query_planner_v1 import plan_query


def test_parallel_fact_split_preserves_named_project_entities():
    single_fact = plan_query("EPC项目清单台账中，宜昌市协和医院项目的结算上限如何约定？")
    assert single_fact.entities == ["宜昌市协和医院项目"]
    assert single_fact.subquestions == []

    parallel = plan_query("天津市两部电梯的型号和载重分别是多少？")
    assert parallel.subquestions == ["型号分别是多少", "载重分别是多少"]

    joint_project = plan_query("公安玉湖及淤泥湖水生态修复项目位于哪个省、哪个县？")
    assert joint_project.subquestions == [
        "公安玉湖哪个省、哪个县",
        "淤泥湖水生态修复项目位于哪个省、哪个县",
    ]

    parallel_categories = plan_query("2025年公司有条件采取深度融合模式项目的新开和新承接项目是哪几个")
    assert parallel_categories.subquestions == ["新开哪几个", "新承接项目是哪几个"]

    parenthetical = plan_query("城综事业部EPC项目设计价值创造统计台账（地下通道项目，靖城路下穿通道）中，结构专业共列了多少项创效策划点？")
    assert parenthetical.subquestions == []

    course_title = plan_query("EPC项目设计管理方法与实务，主要围绕哪几个方面展开介绍")
    assert course_title.subquestions == []
    counted_course = plan_query("《EPC项目设计管理方法与实务》课程分为哪5个章节？")
    assert counted_course.subquestions == ["《EPC项目设计管理方法与实务》课程分为哪5个章节？"]


def test_verified_answer_has_direct_claim_and_citation():
    answer = render(_bundle("VERIFIED", [_evidence("DIRECT")], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}]))
    assert answer["answer_status"] == "ANSWERED"
    assert answer["validation_status"] == "VALID"
    assert answer["claims"][0]["citation_ids"]


def test_scoring_question_uses_the_exact_subject_row_and_score_criterion():
    question = "中建三局局对二公司的2026年设计与技术系统专项责任书中，关于设计建设标准参考手册的评分标准是什么"
    wrong = _evidence("DIRECT", text="表头：序号 | 考核指标 | 考核内容 | 分值 | 评分标准\n行：1 | 设计与技术支持中心能力建设 | 发布《深化设计能力建设实施细则》 | 20 | 未制定细则扣10分。")
    right = _evidence("DIRECT", text="表头：序号 | 考核指标 | 考核内容 | 分值 | 评分标准\n行：4 | 设计管理 | 6.新增不少于2个业态项目设计建设标准参考手册。 | 20 | 6.查看建设标准及发布通知，每少建立一个业态项目设计建设标准参考手册扣1分。")
    wrong.update({"evidence_id": "WRONG", "file_name": "2026专项责任书.docx"})
    right.update({"evidence_id": "RIGHT", "file_name": "2026专项责任书.docx"})
    plan = plan_query(question)
    bundle = _bundle("VERIFIED", [wrong, right], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED"
    assert "每少建立一个业态项目设计建设标准参考手册扣1分" in answer["answer_text"]
    assert "该项分值为20分" in answer["answer_text"]
    assert answer["claims"][0]["evidence_ids"] == ["RIGHT"]


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
    pointer_label = "[最终26个项目成功打造为设计管理示范项目](raw/统计表.md)"
    assert _narrative_count_document_score(pointer_label, question) == 0


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


def test_structured_max_uses_complete_rows_and_answers_requested_risk_field():
    question = "EPC 台账中建筑面积最大的项目是哪个？面积与超概风险如何？"
    evidence = {**_evidence("DIRECT", text="同一来源表格完整行级数据。", location={"table_id": "T1"}), "evidence_id": "TABLE1", "table_id": "T1"}
    rows = [
        {"row_id": "R34", "row_number": 34, "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "V1", "bundle_evidence_id": "TABLE1", "cells": [{"header": "项目名称", "value": "铁投.书香林语项目"}, {"header": "建筑面积(万㎡)", "value": "40.2"}, {"header": "超概风险", "value": "无超概风险"}]},
        {"row_id": "R47", "row_number": 47, "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "V1", "bundle_evidence_id": "TABLE1", "cells": [{"header": "项目名称", "value": "广州何棠下旧改项目"}, {"header": "建筑面积(万㎡)", "value": "56"}, {"header": "超概风险", "value": "现阶段超概风险1.6亿"}]},
        {"row_id": "R55", "row_number": 55, "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "V1", "bundle_evidence_id": "TABLE1", "cells": [{"header": "项目名称", "value": "其他项目"}, {"header": "建筑面积(万㎡)", "value": "31"}, {"header": "超概风险", "value": "无"}]},
    ]
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY", question=question)
    bundle["query_plan"]["aggregation_plan"] = ["MAX"]
    bundle["query_plan"]["metric"] = ["面积", "风险"]
    bundle["structured_evidence_complete"] = True
    bundle["structured_rows"] = rows

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED"
    assert "广州何棠下旧改项目" in answer["answer_text"]
    assert "56万㎡" in answer["answer_text"]
    assert "现阶段超概风险1.6亿" in answer["answer_text"]
    assert "书香林语" not in answer["answer_text"]
    assert validate(answer, bundle)["valid"] is True


def test_structured_max_refuses_to_rank_a_partial_row_set():
    question = "EPC台账中建筑面积最大的项目是哪个？"
    evidence = {**_evidence("DIRECT", text="单行表格命中。", location={"table_id": "T1"}), "evidence_id": "TABLE1", "table_id": "T1"}
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type="AGGREGATION_QUERY", question=question)
    bundle["query_plan"]["aggregation_plan"] = ["MAX"]
    bundle["structured_evidence_complete"] = False
    bundle["structured_rows"] = [{"row_id": "R34", "row_number": 34, "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "bundle_evidence_id": "TABLE1", "cells": [{"header": "建筑面积(万㎡)", "value": "40.2"}]}]

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "40.2" not in answer["answer_text"]


def test_unimplemented_table_sum_does_not_fall_back_to_group_counts():
    question = "项目清单各专业合计金额是多少？"
    evidence = _evidence("DIRECT", text="结构专业 10 万元；建筑专业 20 万元。", location={"table_id": "T1"})
    plan = plan_query(question)
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["structured_evidence_complete"] = True
    bundle["structured_rows"] = [
        {"row_id": "R1", "row_number": 1, "professional": "结构", "bundle_evidence_id": "E1", "cells": [{"header": "金额", "value": "10"}]},
        {"row_id": "R2", "row_number": 2, "professional": "建筑", "bundle_evidence_id": "E1", "cells": [{"header": "金额", "value": "20"}]},
    ]

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "不以分组条数或单行命中代替总额" in answer["answer_text"]
    assert "建筑：1条" not in answer["answer_text"]


def test_table_group_counts_require_complete_structured_rows():
    question = "该表有哪些专业，每个专业多少条？"
    plan = plan_query(question)
    evidence = {**_evidence("DIRECT", text="表头：建筑 | 结构 |", location={"table": 1, "table_id": "T1"}), "table_id": "T1"}
    coverage = [{"subquestion_id": "SQ1", "subquestion": plan.subquestions[0], "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "subquestion": plan.subquestions[1], "coverage_status": "COVERED"}]
    incomplete = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    incomplete["query_plan"] = plan.to_dict()
    incomplete["subquestions"] = plan.subquestions

    partial = render(incomplete)

    assert partial["answer_status"] == "PARTIAL_ANSWER"
    assert "建筑1条" not in partial["answer_text"]
    assert "完整行级明细" in partial["answer_text"]

    complete = {**incomplete, "structured_evidence_complete": True, "structured_rows": [
        {"row_id": "R1", "row_number": 1, "professional": "建筑", "bundle_evidence_id": "E1"},
        {"row_id": "R2", "row_number": 2, "professional": "结构", "bundle_evidence_id": "E1"},
    ]}
    answered = render(complete)

    assert answered["answer_status"] == "ANSWERED"
    assert "建筑：1条" in answered["answer_text"]
    assert "结构：1条" in answered["answer_text"]


def test_table_group_counts_do_not_merge_different_tables_or_source_versions():
    question = "该项目设计价值创造台账有哪些专业，每个专业多少条？"
    plan = plan_query(question)
    evidence = {**_evidence("DIRECT", text="结构化表格命中。", location={"table": 1, "table_id": "T1"}), "table_id": "T1"}
    rows = [
        {"row_id": "R1", "row_number": 1, "professional": "建筑", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1"},
        {"row_id": "R2", "row_number": 2, "professional": "结构", "table_id": "T2", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E2"},
    ]
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions
    bundle["structured_evidence_complete"] = True
    bundle["structured_rows"] = rows

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "多个表格或来源版本" in answer["answer_text"]
    assert "该清单按专业类别列示，共包含2个类别" not in answer["answer_text"]

    bundle["structured_rows"] = [
        {"row_id": "R1", "row_number": 1, "professional": "建筑", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1"},
        {"row_id": "R2", "row_number": 2, "professional": "结构", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA2", "bundle_evidence_id": "E2"},
    ]
    answer = render(bundle)
    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "多个表格或来源版本" in answer["answer_text"]


def test_unsupported_structured_filter_does_not_return_unfiltered_counts():
    question = "该项目台账中，其中收益超过10万元的项目有几个？"
    plan = plan_query(question)
    evidence = {**_evidence("DIRECT", text="同一来源完整表格。", location={"table": 1, "table_id": "T1"}), "table_id": "T1"}
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["structured_evidence_complete"] = True
    bundle["structured_rows"] = [
        {"row_id": "R1", "row_number": 2, "professional": "建筑", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1", "cells": [{"header": "收益", "value": "15"}]},
        {"row_id": "R2", "row_number": 3, "professional": "结构", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1", "cells": [{"header": "收益", "value": "5"}]},
    ]

    answer = render(bundle)

    assert "FILTER" in plan.aggregation_plan
    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "不返回未筛选的全表统计" in answer["answer_text"]
    assert "建筑：1条" not in answer["answer_text"]
    assert validate(answer, bundle)["valid"] is True


def test_supported_benefit_marker_filter_reads_raw_table_cells():
    question = "该项目设计价值创造台账中，各专业多少条？其中增加效益多少条？"
    plan = plan_query(question)
    evidence = {**_evidence("DIRECT", text="同一来源完整表格。", location={"table": 1, "table_id": "T1"}), "table_id": "T1"}
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["structured_evidence_complete"] = True
    bundle["structured_rows"] = [
        {"row_id": "R1", "row_number": 2, "professional": "建筑", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1", "cells": [{"header": "价值创造分析", "value": "保持原设计"}]},
        {"row_id": "R2", "row_number": 3, "professional": "结构", "table_id": "T1", "source_path": "[LOCAL_PATH_REDACTED]", "source_version": "SHA1", "bundle_evidence_id": "E1", "cells": [{"header": "价值创造分析", "value": "增加效益：减少材料成本"}]},
    ]

    answer = render(bundle)

    assert "FILTER" in plan.aggregation_plan
    assert answer["answer_status"] == "ANSWERED"
    assert "按“价值创造分析”中包含增加效益、增效、收益或利润表述统计，共1条" in answer["answer_text"]
    assert validate(answer, bundle)["valid"] is True


def test_direct_claim_must_cover_its_assigned_issue_subquestion():
    question = "中建三局党委巡察二公司华南公司党委反馈问题，关于中台能力方面的问题是什么"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="在二公司设计管理工作中，中建三局作为上级单位，提供设计管理的制度框架、标准体系和技术指导。")
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": f"SQ{i}", "coverage_status": "COVERED"} for i, _ in enumerate(plan.subquestions, start=1)], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "中建三局作为上级单位" not in answer["answer_text"]
    assert "中台能力" in answer["answer_text"] or "问题是什么" in answer["answer_text"]


def test_explicit_six_item_question_requires_six_enumerated_items():
    question = "二公司设计管理部的主要职责有哪 6 项？"
    plan = plan_query(question)
    assert plan.subquestions == [question]
    short = _evidence("DIRECT", text="中建三局第二建设公司设计管理部是公司设计管理工作的核心部门，负责体系建设和EPC项目设计全过程管理。")
    bundle = _bundle("VERIFIED", [short], [{"subquestion_id": "SQ1", "subquestion": question, "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    partial = render(bundle)

    assert partial["answer_status"] == "PARTIAL_ANSWER"
    assert "未在本次回答中完整回应" in partial["answer_text"]
    assert "核心部门" in partial["answer_text"]

    complete_text = "职责包括：设计管理体系建设和维护；EPC项目设计支持与策划；设计评审与评估管理；设计资源库建设；设计人才培养与能力建设；制度文件编制与更新。"
    complete = _evidence("DIRECT", text=complete_text)
    full_bundle = {**bundle, "candidate_evidence": [complete], "verified_evidence": [complete]}
    answered = render(full_bundle)

    assert answered["answer_status"] == "ANSWERED"
    assert all(term in answered["answer_text"] for term in ("设计管理体系建设和维护", "EPC项目设计支持与策划", "制度文件编制与更新"))


def test_eight_dimension_question_rejects_one_dimension_as_complete():
    question = "EPC 项目设计管理评价表是多少分制？覆盖哪 8 个维度、各多少标准分？"
    plan = plan_query(question)
    evidence = {**_evidence("DIRECT", text="表头：维度 | 标准分 | 关键评分项 行：设计策划管理 | 20 | 设计评估、对标分析和设计任务书", location={"table": 1, "table_id": "T1"}), "table_id": "T1"}
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": f"SQ{i}", "subquestion": q, "coverage_status": "COVERED"} for i, q in enumerate(plan.subquestions, start=1)], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "未在本次回答中完整回应" in answer["answer_text"]


def test_government_question_needs_a_named_government_not_a_category():
    question = "二公司设计资源库战略协议中合作的政府单位是哪一家？"
    generic = _evidence("DIRECT", text="战略合作协议是二公司与各设计院、政府签订的合作框架协议汇总。")
    partial = render(_bundle("VERIFIED", [generic], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert partial["answer_status"] == "PARTIAL_ANSWER"

    named = {**generic, "evidence_id": "E2", "text": "该战略合作框架协议甲方为苏州市吴中区人民政府。"}
    answered = render(_bundle("VERIFIED", [named], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert answered["answer_status"] == "ANSWERED"
    assert "苏州市吴中区人民政府" in answered["answer_text"]


def test_design_efficiency_threshold_claim_keeps_all_categories_or_fails_closed():
    question = '评价表中"设计创效率"的量化门槛（红线）是多少？'
    full = _evidence("DIRECT", text='设计创效率门槛（量化红线）：新开房建 EPC ≥4%（方案阶段介入 ≥6%）；新开线性工程 ≥2.5%；非传统专业工程 ≥3%。得分为“创效完成率×5分”，满分 6 分。')
    answered = render(_bundle("VERIFIED", [full], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert answered["answer_status"] == "ANSWERED"
    assert all(value in answered["answer_text"] for value in ("4%", "6%", "2.5%", "3%"))

    partial_text = _evidence("DIRECT", text="设计创效率门槛：新开房建EPC≥4%，方案阶段介入≥6%。")
    partial = render(_bundle("VERIFIED", [partial_text], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], question=question))
    assert partial["answer_status"] == "PARTIAL_ANSWER"


def test_certification_list_does_not_substitute_for_green_low_carbon_metric():
    question = "沈阳中心大厦的绿色低碳指标是多少？目标是哪四项认证？"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="沈阳中心大厦绿色建筑四项认证目标：绿建三星级、LEED金级、WELL铂金级、净零碳建筑卓越级。")
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": f"SQ{i}", "subquestion": subquestion, "coverage_status": "COVERED"} for i, subquestion in enumerate(plan.subquestions, start=1)], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "净零碳建筑卓越级" in answer["answer_text"]
    assert "绿色低碳指标" in answer["answer_text"]


def test_approved_hainan_gold_source_covers_count_and_beam_measure_separately():
    question = "海南中心塔冠施工设置多少个支撑胎架？针对主梁变形采取了什么措施？"
    plan = plan_query(question)
    evidence = _evidence(
        "DIRECT",
        text="""塔冠施工过程共设有22个胎架。支撑胎架采用塔吊标准节和自制胎架相结合，标准节部分采用TC6513-8(ZL标准节)组成，上部采用自制调节段部分，均采用销轴连接。\n4.前置风险识别与全维度预控策划：采用midas Gen开展仿真，精准预判主梁竖向挠度。\nZ向变形 max=22.5mm解决方案：工厂预起拱40mm（已与设计沟通）\n梁底部增加D300*16mm的圆管斜撑回顶。""",
    )
    evidence["source_id"] = "V262-hainan-approved-source"
    coverage = [
        {"subquestion_id": f"SQ{index}", "subquestion": subquestion, "coverage_status": "COVERED"}
        for index, subquestion in enumerate(plan.subquestions, start=1)
    ]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED"
    direct = {claim["subquestion_id"]: claim for claim in answer["claims"] if claim["claim_type"] == "DIRECT"}
    assert set(direct) == {"SQ1", "SQ2"}
    assert "22个胎架" in direct["SQ1"]["claim_text"]
    assert all(term in direct["SQ2"]["claim_text"] for term in ("Z向变形", "预起拱40mm", "D300*16mm"))
    assert validate(answer, bundle)["valid"] is True

    insufficient = {**bundle, "verified_evidence": [{**evidence, "text": "塔冠施工过程共设有22个胎架。"}]}
    partial = render(insufficient)
    assert partial["answer_status"] == "PARTIAL_ANSWER"
    assert "未在本次回答中完整回应" in partial["answer_text"]


def test_single_claim_cannot_answer_both_targets_in_a_shared_predicate_question():
    question = "三峡钱塘风电项目的装机容量和地点是什么？"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="装机容量为 100 MW。")
    coverage = [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "COVERED"}]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions
    answer = _answer(bundle, "ANSWERED", [_claim("C1", "DIRECT", "SQ1", "装机容量为 100 MW。", ["E1"])], [])

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "SQ2" in answer["uncovered_subquestions"]
    assert "地点" in answer["answer_text"]


def test_field_list_claim_covers_question_worded_as_containment():
    question = "《设计方案比选提示清单》覆盖多少项比选内容？每项包含哪些字段？"
    plan = plan_query(question)
    text = "覆盖18+项高频比选内容，每项含专业类别、比选项目、方案一到三、技术分析、商务分析、比选结果和比选阶段。"
    evidence = _evidence("DIRECT", text=text)
    coverage = [{"subquestion_id": f"SQ{i}", "subquestion": subquestion, "coverage_status": "COVERED"} for i, subquestion in enumerate(plan.subquestions, start=1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = _answer(bundle, "ANSWERED", [_claim("C1", "DIRECT", "SQ1", text, ["E1"])], [])

    assert answer["answer_status"] == "ANSWERED"
    assert "未在本次回答中完整回应" not in answer["answer_text"]


def test_scale_and_schedule_labels_cover_parallel_fact_subquestions():
    question = "中国移动（呼和浩特）方舱式数据中心项目的规模、装机能力与工期节点是多少？"
    plan = plan_query(question)
    text = "总建筑面积54170.7㎡，含2栋数据中心；装机能力2876架；合同开工日期2026年3月16日，第一批次交付日期2026年9月20日，第二批次交付日期2027年12月31日，总工期656天。"
    evidence = _evidence("DIRECT", text=text)
    coverage = [{"subquestion_id": f"SQ{i}", "subquestion": subquestion, "coverage_status": "COVERED"} for i, subquestion in enumerate(plan.subquestions, start=1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = _answer(bundle, "ANSWERED", [_claim("C1", "DIRECT", "SQ1", text, ["E1"])], [])

    assert answer["answer_status"] == "ANSWERED"
    assert not answer["uncovered_subquestions"]


def test_main_building_indicators_require_multiple_labelled_source_metrics():
    question = "深圳华为百草园城市更新项目的合同额、工期与主要建筑指标是多少？"
    plan = plan_query(question)
    coverage = [{"subquestion_id": f"SQ{i}", "subquestion": subquestion, "coverage_status": "COVERED"} for i, subquestion in enumerate(plan.subquestions, start=1)]

    complete_text = "合同额10.9亿元；合同工期1277天；占地面积9.7万m²；总建筑面积31.66万m²；北塔3792㎡/F、高154.5m；南塔3289㎡/F、高87.8m。"
    complete_evidence = _evidence("DIRECT", text=complete_text)
    complete_bundle = _bundle("VERIFIED", [complete_evidence], coverage, query_type=plan.query_type, question=question)
    complete_bundle["query_plan"] = plan.to_dict()
    complete_bundle["subquestions"] = plan.subquestions
    complete = _answer(complete_bundle, "ANSWERED", [_claim("C1", "DIRECT", "SQ1", complete_text, ["E1"])], [])

    unclear_text = "合同额10.9亿元；合同工期1277天；9.7；31.66；154.5m；87.8m。"
    unclear_evidence = _evidence("DIRECT", text=unclear_text)
    unclear_bundle = _bundle("VERIFIED", [unclear_evidence], coverage, query_type=plan.query_type, question=question)
    unclear_bundle["query_plan"] = plan.to_dict()
    unclear_bundle["subquestions"] = plan.subquestions
    unclear = _answer(unclear_bundle, "ANSWERED", [_claim("C1", "DIRECT", "SQ1", unclear_text, ["E1"])], [])

    assert complete["answer_status"] == "ANSWERED"
    assert unclear["answer_status"] == "PARTIAL_ANSWER"
    assert "SQ3" in unclear["uncovered_subquestions"]


def test_task_book_directory_link_cannot_supply_project_count_or_industries():
    question = "设计任务书汇编收录了多少个项目的任务书？覆盖哪些业态？"
    plan = plan_query(question)
    coverage = [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "COVERED"}]
    link_labels = (
        "[[raw/设计支持/设计任务书|设计任务书文件夹（26个项目）]]",
        "[设计任务书文件夹（26个项目）](raw/设计支持/设计任务书)",
    )
    for link in link_labels:
        text = f"编制明确的设计任务书，规定设计范围、技术标准、进度要求和交付成果，作为设计工作的依据。\n关键文件：{link}"
        evidence = _evidence("DIRECT", text=text)
        bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
        bundle["query_plan"] = plan.to_dict()

        answer = render(bundle)

        assert answer["answer_status"] == "PARTIAL_ANSWER"
        assert "26个项目" not in answer["answer_text"]
        assert "目录链接标签不作为" in answer["answer_text"]


def test_task_book_count_and_industries_need_body_support_for_both_facts():
    question = "设计任务书汇编收录了多少个项目的任务书？覆盖哪些业态？"
    evidence = _evidence("DIRECT", text="设计任务书汇编收录了26个项目的任务书，覆盖住宅、医院和学校三类业态。")
    plan = plan_query(question)
    coverage = [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "COVERED"}]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED"
    assert "26 个项目" in answer["answer_text"]
    assert "住宅、医院和学校" in answer["answer_text"]


def test_answer_becomes_partial_when_a_required_clause_has_no_answer_claim():
    question = "设计评估的流程分为哪三步？评估结论应用于哪三个方面？"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="评估报告编制、评审与交底、评估应用。")
    coverage = [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}, {"subquestion_id": "SQ2", "coverage_status": "COVERED"}]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions
    unrelated = _claim("C1", "DIRECT", "SQ1", "设计评估主要包括整体结论经过量化评估、设计评估。", ["E1"])
    both_clauses = _claim("C1", "DIRECT", "SQ1", "设计评估流程分为资料收集、报告编制、评审交底三步；评估结论应用于设计合约规划、风险识别和方案比选等三个方面。", ["E1"])

    partial = _answer(bundle, "ANSWERED", [unrelated], [])
    complete = _answer(bundle, "ANSWERED", [both_clauses], [])

    assert partial["answer_status"] == "PARTIAL_ANSWER"
    assert "SQ2" in partial["uncovered_subquestions"]
    assert "设计评估主要包括整体结论经过量化评估" not in partial["answer_text"]
    assert partial["answer_text"].count("未在本次回答中完整回应") == 2
    assert complete["answer_status"] == "ANSWERED"


def _bundle(status, evidence, coverage, query_type="SOURCE_LOOKUP", question="测试问题"):
    return {"query_id": "Q", "question": question, "query_plan": {"query_type": query_type, "aggregation_plan": []}, "bundle_status": status, "candidate_evidence": evidence, "verified_evidence": evidence if status != "CONFLICTING_EVIDENCE" else [], "supporting_evidence": [], "conflicting_evidence": evidence if status == "CONFLICTING_EVIDENCE" else [], "excluded_evidence": [], "coverage_map": coverage, "conflict_map": {}, "structured_fact_map": {}}


def _evidence(role, text="已核查的直接事实", location=None):
    return {"evidence_id": "E1", "role": role, "text": text, "candidate_rank": 1, "document_id": "D1", "source_path": "[LOCAL_PATH_REDACTED]", "file_name": "source.md", "heading_path": "章节", "location": location or {"line_start": 1, "line_end": 1}}


def test_approved_gold_multifact_claims_bind_to_the_requested_subquestions():
    cases = (
        (
            "扬州大运河“十里外滩”项目设计策划评审后形成了几项督办事项？要求何时完成？",
            "扬州大运河十里外滩督办清单（7 项修改事宜，限 6.1–6.15 完成）",
            2,
        ),
        (
            "海外数据中心业务累计承接、已交付的项目数，以及施工面积和总容量分别是多少？",
            "海外数据中心业务累计承接数据中心项目41个，已交付13个，施工面积超100万㎡，总容量超3GW。",
            4,
        ),
        (
            "EPC项目清单台账中，光谷国际社区一标段的合同额、建筑面积和设计单位分别是什么？",
            "光谷国际社区一标段 | 合同额：10.19亿元 | 建筑面积：19.8万㎡ | 设计单位：上海联创设计集团股份有限公司",
            3,
        ),
    )
    for question, source_text, subquestion_count in cases:
        plan = plan_query(question)
        evidence = _evidence("DIRECT", text=source_text)
        evidence.update({"evidence_id": "E1", "source_id": "V262-TEST", "file_name": "approved-source.md"})
        coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, subquestion_count + 1)]
        bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
        bundle["query_plan"] = plan.to_dict()
        bundle["subquestions"] = plan.subquestions

        answer = render(bundle)

        assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
        assert {claim["subquestion_id"] for claim in answer["claims"] if claim["claim_type"] == "DIRECT"} == {f"SQ{index}" for index in range(1, subquestion_count + 1)}
        assert "暂不能确认" not in answer["answer_text"]


def test_owner_source_rescue_renders_the_duty_count_and_deadline_from_the_source():
    question = "扬州大运河“十里外滩”项目设计策划评审后形成了几项督办事项？要求何时完成？"
    source_text = "评审与督办闭环：督办清单（7 项修改事宜，限 6.1–6.15 完成）。"
    evidence = _evidence("DIRECT", text=source_text)
    evidence.update({
        "source_id": "BASE-STAGING-SOURCE",
        "candidate_origin": "OWNER_ANSWER_GOLD_SOURCE_RESCUE",
        "file_name": "设计策划评审.md",
        "source_path": r"[LOCAL_PATH_REDACTED]��\设计策划评审.md",
    })
    plan = plan_query(question)
    coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, len(plan.subquestions) + 1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert {claim["subquestion_id"] for claim in answer["claims"] if claim["claim_type"] == "DIRECT"} == {"SQ1", "SQ2"}
    assert "7 项" in answer["answer_text"] and "6.1–6.15" in answer["answer_text"]


def test_course_chapter_answer_requires_all_five_source_headings():
    question = "《EPC项目设计管理方法与实务》课程分为哪5个章节？"
    titles = (
        "背景介绍",
        "设计管理基本动作与要素",
        "设计管理关键动作实施要点",
        "全专业设计技术管控要点",
        "存在的问题与建议",
    )
    evidence = []
    intro = _evidence("DIRECT", text="[/body/p[@paraId=0]] 课程的整体框架共分为五个章节。")
    intro.update({"evidence_id": "E0", "source_id": "V262-COURSE", "file_name": "EPC方法与实务.md"})
    evidence.append(intro)
    for index, title in enumerate(titles, start=1):
        item = _evidence("DIRECT", text=f"[/body/p[@paraId={index}]] {('一', '二', '三', '四', '五')[index - 1]} {title}")
        item.update({"evidence_id": f"E{index}", "source_id": "V262-COURSE", "file_name": "EPC方法与实务.md"})
        evidence.append(item)
    plan = plan_query(question)
    bundle = _bundle("VERIFIED", evidence, [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert all(title in answer["answer_text"] for title in titles)
    assert len(answer["citations"]) == 6


def test_company_epc_evaluation_dimensions_stay_in_the_named_complete_table():
    question = "《公司EPC项目设计管理评价表》采用多少分制？9个评价维度分别是什么？"
    source_path = "[LOCAL_PATH_REDACTED]��院项目.docx"
    source_version = "sha-source"
    table_id = "target-table"
    labels = (
        "设计管理架构(5分)",
        "设计策划管理 (20分)",
        "设计计划管理(15分)",
        "限额设计管理(15分)",
        "设计优化管理(15分)",
        "设计质量管理(10分)",
        "材料设备选型报审(5分)",
        "设计报批报建(5分)",
        "设计复盘总结(10分)",
    )
    evidence = []
    structured_rows = []
    for index, label in enumerate((*labels, labels[4]), start=1):
        item = _evidence("DIRECT", text=f"行：{index} | {label}", location={"table_id": table_id, "row_start": index, "row_end": index})
        item.update({"evidence_id": f"E{index}", "source_path": source_path, "source_version": source_version, "file_name": "丽水医院项目.docx", "heading_path": "公司EPC项目设计管理评价表", "table_id": table_id})
        evidence.append(item)
        structured_rows.append({
            "source_path": source_path,
            "source_version": source_version,
            "table_id": table_id,
            "expected_table_row_count": 10,
            "row_id": f"R{index}",
            "row_number": index,
            "cells": [{"value": str(index)}, {"value": label}],
        })
    unrelated = _evidence("DIRECT", text="行：15 | 设计创效率 | 常熟项目")
    unrelated.update({"evidence_id": "OTHER", "source_path": "[LOCAL_PATH_REDACTED]��创造.xlsx", "source_version": "sha-other", "file_name": "常熟台账.xlsx", "heading_path": "直属分公司设计价值创造统计表", "table_id": "other-table"})
    evidence.append(unrelated)
    structured_rows.append({
        "source_path": unrelated["source_path"],
        "source_version": unrelated["source_version"],
        "table_id": unrelated["table_id"],
        "expected_table_row_count": 1,
        "row_id": "OTHER-ROW",
        "row_number": 15,
        "cells": [{"value": "15"}, {"value": "设计创效率"}],
    })
    plan = plan_query(question)
    coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, len(plan.subquestions) + 1)]
    bundle = _bundle("VERIFIED", evidence, coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions
    bundle["structured_rows"] = structured_rows

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert "采用100分制" in answer["answer_text"]
    assert "设计创效率" not in answer["answer_text"]
    assert len([line for line in answer["answer_text"].splitlines() if ". " in line]) == 9
    assert len(answer["citations"]) == 9
    assert all(citation["source_path"] == source_path for citation in answer["citations"])


def test_huawei_baicaoyuan_returns_source_facts_without_inventing_a_total():
    question = "华为百草园项目通过设计优化完成多少项优化、创效多少？"
    evidence = _evidence(
        "DIRECT",
        text="桩基支护优化22项，主体结构优化：塔楼结构体系优化。图纸下发前桩基支护优化22项，主体结构优化38项，累计技术创效2473万元车道管综。",
    )
    evidence.update({"source_id": "V262-BAICAOYUAN", "file_name": "百草园超高层产品线观摩材料.md"})
    plan = plan_query(question)
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "桩基支护优化22项" in answer["answer_text"]
    assert "主体结构优化38项" in answer["answer_text"]
    assert "累计技术创效2473万元" in answer["answer_text"]
    assert "不将分项数量相加" in answer["answer_text"]
    assert "60项" not in answer["answer_text"]


def test_dimension_counter_uses_the_three_requested_dimensions_not_the_summary_bullet():
    question = "设计创效案例库中，每个案例的实施效果从哪三个维度评估？"
    source_text = "- 案例统一结构：每个创效案例按项目名称、专业、设计阶段组织，实施效果从设计、建造、商务三个维度评估。"
    evidence = _evidence("DIRECT", text=source_text)
    evidence.update({"source_id": "V262-CASEBOOK", "file_name": "设计创效案例库.md"})
    plan = plan_query(question)
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert all(name in answer["answer_text"] for name in ("设计", "建造", "商务"))


def test_scheme_comparison_claims_use_the_same_source_for_dimensions_and_steps():
    question = "方案比选的评价维度有哪五方面？工作流程分几步？"
    source_text = (
        "- **评价维度**：技术可行性、经济合理性、施工便利性、工期影响、运维成本\n"
        "- **工作流程**：明确比选目标 → 编制比选方案 → 组织评审 → 形成结论"
    )
    evidence = _evidence("DIRECT", text=source_text)
    evidence.update({"file_name": "方案比选.md", "source_path": "[LOCAL_PATH_REDACTED]��/方案比选.md"})
    plan = plan_query(question)
    coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, len(plan.subquestions) + 1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert all(value in answer["answer_text"] for value in ("技术可行性", "经济合理性", "施工便利性", "工期影响", "运维成本"))
    assert "工作流程分为4步" in answer["answer_text"]


def test_workflow_step_counter_ignores_adjacent_summary_bullets():
    question = "设计价值创造的工作流程是哪四步？"
    source_text = "- **价值创造方式**：设计方案优化、材料设备选型优化、施工工艺优化 - **管理工具**：价值创造清单、价值工程分析、成本效益分析 - **工作流程**：识别价值点 → 分析可行性 → 实施优化 → 验证效果 - **量化指标**：造价节约、工期缩短、品质提升、运维成本降低。"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text=source_text)
    bundle = _bundle("VERIFIED", [evidence], [{"subquestion_id": "SQ1", "coverage_status": "COVERED"}], query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions
    claim = _claim("C1", "DIRECT", "SQ1", source_text, ["E1"])

    answer = _answer(bundle, "ANSWERED", [claim], [])

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert "未在本次回答中完整回应" not in answer["answer_text"]


def test_owner_demand_list_explicit_count_covers_the_item_count_subquestion():
    question = "广西体育专科学校项目业主需求清单的提出时间与条目数量是多少？"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="业主需求清单提出时间为2020.07，包括总平面、建筑、结构、机电等专业，共126项。")
    coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, len(plan.subquestions) + 1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "ANSWERED", answer["answer_text"]
    assert "2020.07" in answer["answer_text"] and "126项" in answer["answer_text"]


def test_demand_list_needs_an_item_total_not_an_unrelated_numeric_count():
    question = "广西体育专科学校项目业主需求清单的提出时间与条目数量是多少？"
    plan = plan_query(question)
    evidence = _evidence("DIRECT", text="业主需求清单提出时间为2020.07；方案涉及3个专业，共2次评审。")
    coverage = [{"subquestion_id": f"SQ{index}", "coverage_status": "COVERED"} for index in range(1, len(plan.subquestions) + 1)]
    bundle = _bundle("VERIFIED", [evidence], coverage, query_type=plan.query_type, question=question)
    bundle["query_plan"] = plan.to_dict()
    bundle["subquestions"] = plan.subquestions

    answer = render(bundle)

    assert answer["answer_status"] == "PARTIAL_ANSWER"
    assert "条目数量是多少" in answer["answer_text"]
