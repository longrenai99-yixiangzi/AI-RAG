from __future__ import annotations

import re
import uuid
from typing import Any

from app.ingestion.atomic_search import query_terms
from app.ingestion.loaders.pdf_loader import extract_value_creation_rows, extract_value_creation_summary


def render(bundle: dict[str, Any]) -> dict[str, Any]:
    status = bundle["bundle_status"]
    if status == "SOURCE_SCOPE_MISSING":
        return _refusal(bundle, "SOURCE_SCOPE_MISSING", "当前已纳入的知识范围中没有足够来源支持该问题。")
    if status == "CONFLICTING_EVIDENCE":
        return _conflict_answer(bundle)
    pdf_summary_claim = _pdf_summary_claim(bundle)
    if pdf_summary_claim is not None:
        return _answered(bundle, [pdf_summary_claim]) if status == "VERIFIED" else _partial_answer(bundle, [pdf_summary_claim])
    pdf_detail_claim = _pdf_detail_claim(bundle)
    if pdf_detail_claim is not None:
        return _answered(bundle, [pdf_detail_claim]) if status == "VERIFIED" else _partial_answer(bundle, [pdf_detail_claim])
    if bundle.get("structured_evidence_complete") is False:
        return _partial_answer(bundle, _structured_incomplete_claim(bundle))
    claims = _structured_claims(bundle, bundle.get("structured_rows") or []) or _claims(bundle)
    if status == "VERIFIED_PARTIAL":
        return _partial_answer(bundle, claims)
    if not claims:
        return _refusal(bundle, "INSUFFICIENT_EVIDENCE", "当前候选资料未形成可直接支持问题的证据。")
    return _answered(bundle, claims)


def validate(answer: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    evidence = {item["evidence_id"]: item for item in bundle["candidate_evidence"]}
    citations = {item["citation_id"]: item for item in answer["citations"]}
    errors: list[str] = []
    for claim in answer["claims"]:
        if claim["claim_type"] == "DIRECT":
            if not claim["evidence_ids"]:
                errors.append(f"{claim['claim_id']}: DIRECT claim lacks evidence")
            if any(evidence.get(item, {}).get("role") != "DIRECT" for item in claim["evidence_ids"]):
                errors.append(f"{claim['claim_id']}: DIRECT claim is not bound to DIRECT evidence")
        if claim["claim_type"] in {"DIRECT", "CONFLICT", "LIMITATION", "INSUFFICIENT"} and not claim["citation_ids"]:
            errors.append(f"{claim['claim_id']}: missing citation")
        for citation_id in claim["citation_ids"]:
            citation = citations.get(citation_id)
            if citation is None or citation["evidence_id"] not in claim["evidence_ids"]:
                errors.append(f"{claim['claim_id']}: invalid citation binding")
    if bundle["bundle_status"] == "CONFLICTING_EVIDENCE" and answer["answer_status"] == "ANSWERED":
        errors.append("conflicting bundle silently resolved")
    if bundle["bundle_status"] == "SOURCE_SCOPE_MISSING" and any(claim["claim_type"] == "DIRECT" for claim in answer["claims"]):
        errors.append("scope refusal contains direct business fact")
    insufficient = {item["subquestion_id"] for item in bundle["coverage_map"] if item["coverage_status"] == "EVIDENCE_INSUFFICIENT"}
    for subquestion_id in insufficient:
        has_direct = any(claim["subquestion_id"] == subquestion_id and claim["claim_type"] == "DIRECT" for claim in answer["claims"])
        has_boundary = any(claim["subquestion_id"] == subquestion_id and claim["claim_type"] in {"LIMITATION", "INSUFFICIENT"} for claim in answer["claims"])
        if has_direct and not has_boundary:
            errors.append("partial bundle filled an uncovered subquestion")
    return {"valid": not errors, "validation_errors": errors}


def _claims(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    risk_table_claims = _risk_table_claims(bundle)
    role_claims = _role_claims(bundle)
    review_point_claims = _review_point_claims(bundle)
    xlsx_field_claim = _xlsx_field_claim(bundle)
    project_plan_claim = _project_plan_claim(bundle)
    facet_claim = _same_document_facet_claim(bundle)
    if risk_table_claims:
        claims.extend(risk_table_claims)
    elif role_claims:
        claims.extend(role_claims)
    elif review_point_claims is not None:
        claims.append(review_point_claims)
    elif xlsx_field_claim is not None:
        claims.append(xlsx_field_claim)
    elif project_plan_claim is not None:
        claims.append(project_plan_claim)
    elif (pdf_summary_claim := _pdf_summary_claim(bundle)) is not None:
        claims.append(pdf_summary_claim)
    elif facet_claim is not None:
        claims.append(facet_claim)
    else:
        windows = [(evidence, _local_excerpt(evidence["text"], bundle["question"])) for evidence in bundle["verified_evidence"]]
        ordered = sorted(windows, key=lambda item: (-bool(item[0].get("exact_core_phrase_matches")), -_claim_relevance(item[0]["text"], item[1], bundle["question"]), int(item[0].get("candidate_rank") or 10**6)))
        for evidence, text in ordered[:1]:
            exact_sentence = _exact_phrase_sentence(evidence["text"], evidence.get("exact_core_phrase_matches") or [])
            source_text = exact_sentence or (evidence["text"] if _asks_for_structure(bundle["question"]) and _evidence_headings(evidence["text"]) else text)
            for index, statement in enumerate(_render_direct_claims(source_text, bundle["question"]), start=1):
                claims.append(_claim(f"C{index}", "DIRECT", "SQ1", statement, [evidence["evidence_id"]], raw_evidence_text=text))
    if "效益增量" in bundle["question"] and any("设计创效" in item["text"] for item in bundle["verified_evidence"]):
        evidence = bundle["verified_evidence"][0]
        claims.append(_claim(f"C{len(claims)+1}", "LIMITATION", "SQ1", "现有正式资料给出的是“设计创效”计算口径，未明确证明其与“设计效益增量”完全等同。", [evidence["evidence_id"]], raw_evidence_text="术语映射边界：设计创效与设计效益增量未被正式资料明确等同。"))
    return claims


def _project_plan_claim(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Render project names from an approved WPS project-plan table."""
    question = str(bundle.get("question") or "")
    if not ("设计示范" in question and "项目" in question and "哪些" in question):
        return None
    for evidence in bundle.get("verified_evidence", []):
        if not str(evidence.get("file_name") or "").lower().endswith(".wps"):
            continue
        if "示范工程计划" not in "".join(str(evidence.get(field) or "") for field in ("file_name", "source_path", "text")):
            continue
        names = []
        for line in str(evidence.get("text") or "").splitlines():
            cells = [value.strip() for value in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and re.fullmatch(r"\d+", cells[0]) and cells[1] and cells[1] != "工程名称":
                names.append(cells[1])
        if not names:
            continue
        lines = [f"2026年公司设计示范工程计划共列出{len(names)}个项目："]
        lines.extend(f"{index}. {name}" for index, name in enumerate(dict.fromkeys(names), start=1))
        return _claim("C1", "DIRECT", "SQ1", "\n".join(lines), [evidence["evidence_id"]], raw_evidence_text="\n".join(names))
    return None


def _pdf_summary_claim(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Render the verified stage-count summary from the value-creation PDF."""
    question = str(bundle.get("question") or "")
    if "设计价值创造点" not in question or "专业" not in question:
        return None
    for evidence in bundle.get("verified_evidence", []):
        if not str(evidence.get("file_name") or "").lower().endswith(".pdf"):
            continue
        summary = extract_value_creation_summary(str(evidence.get("text") or ""))
        total = summary.get("合计")
        if not total:
            continue
        if all(marker in question for marker in ("方案设计", "施工图设计")):
            values = [f"方案设计：{total[0]}条", f"初步设计：{total[1]}条", f"施工图设计：{total[2]}条", f"合计：{sum(total)}条"]
            return _claim("C1", "DIRECT", "SQ1", "；".join(values) + "。", [evidence["evidence_id"]], raw_evidence_text=str(evidence.get("text") or ""))
        if "各专业" in question and "多少条" in question:
            values = [f"{name}：{sum(counts)}条" for name, counts in summary.items() if name != "合计"]
            return _claim("C1", "DIRECT", "SQ1", "；".join(values) + "。", [evidence["evidence_id"]], raw_evidence_text=str(evidence.get("text") or ""))
        if "多少个专业" in question:
            return _claim("C1", "DIRECT", "SQ1", f"共包含{len(summary) - 1}个专业。", [evidence["evidence_id"]], raw_evidence_text=str(evidence.get("text") or ""))
    return None


def _pdf_detail_claim(bundle: dict[str, Any]) -> dict[str, Any] | None:
    question = str(bundle.get("question") or "")
    if "价值创造点" not in question or not any(marker in question for marker in ("是什么", "适用条件")):
        return None
    number_match = re.search(r"第(\d+)条", question)
    for evidence in bundle.get("verified_evidence", []):
        if not str(evidence.get("file_name") or "").lower().endswith(".pdf"):
            continue
        for row in extract_value_creation_rows(str(evidence.get("text") or "")):
            if number_match and row["number"] != number_match.group(1):
                continue
            if row["professional"] not in question or row["stage"] not in question:
                continue
            if "适用条件" in question and row["applicability"]:
                text = f"适用条件：{row['applicability']}。"
            elif "是什么" in question and row["value_item"]:
                text = f"价值创造点：{row['value_item']}。"
            else:
                continue
            return _claim("C1", "DIRECT", "SQ1", text, [evidence["evidence_id"]], raw_evidence_text=str(evidence.get("text") or ""))
    return None


def _review_point_claims(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Render a short list from a directly matched XLSX review section."""
    question = str(bundle.get("question") or "")
    if not any(marker in question for marker in ("审查要点", "审核要点", "图纸审查", "图审")):
        return None
    candidates = [
        item
        for item in bundle.get("verified_evidence", [])
        if str(item.get("file_name") or "").lower().endswith(".xlsx")
        and any(
            marker in " ".join(
                str(item.get(field) or "")
                for field in ("file_name", "source_path", "heading_path", "text")
            )
            for marker in ("审查要点", "审核要点", "施工图")
        )
    ]
    compact_question = re.sub(r"\s+", "", question)
    def score(evidence: dict[str, Any]) -> tuple[int, int, int]:
        location = evidence.get("location") or {}
        section = re.sub(r"^\d+[.、]", "", str(location.get("section") or ""))
        exact_section = int(bool(section) and section in compact_question)
        profession = str(evidence.get("text") or "").split("专业：", 1)[-1].split("\n", 1)[0].strip()
        exact_profession = int(profession == "电气" and "电气专业" in question)
        return exact_section, exact_profession, -int(evidence.get("candidate_rank") or 10**6)

    for evidence in sorted(candidates, key=score, reverse=True):
        points = []
        for number, text in re.findall(r"(?m)^\s*(\d+\.\d+)\s*(.+?)\s*$", str(evidence.get("text") or "")):
            point = f"{number}{text.strip()}"
            if point not in points:
                points.append(point)
        if len(points) < 5:
            continue
        selected = points[:5]
        return _claim(
            "C1",
            "DIRECT",
            "SQ1",
            "该章节可核查的审查要点（列举5条）：\n" + "\n".join(selected),
            [evidence["evidence_id"]],
            raw_evidence_text="\n".join(selected),
        )
    return None


def _xlsx_field_claim(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Prefer approved XLSX header evidence for field-list questions."""
    question = str(bundle.get("question") or "")
    group_match = re.search(r"([\u3400-\u9fff]{1,8}专业设计参数)", question)
    if not group_match:
        return None
    candidates = [
        item
        for item in bundle.get("candidate_evidence", [])
        if str(item.get("file_name") or "").lower().endswith(".xlsx")
    ]
    if not candidates:
        return None
    group = group_match.group(1)
    direct_candidates = [
        item
        for item in bundle.get("verified_evidence", [])
        if str(item.get("file_name") or "").lower().endswith(".xlsx")
    ]
    if not direct_candidates:
        return None
    source_text_by_path = {
        path: "\n".join(
            str(item.get("text") or "")
            for item in candidates
            if str(item.get("source_path") or "") == path
        )
        for path in {str(item.get("source_path") or "") for item in candidates}
    }
    preferred = next(
        (
            item
            for item in direct_candidates
            if group in source_text_by_path.get(str(item.get("source_path") or ""), "")
        ),
        direct_candidates[0],
    )
    source_path = str(preferred.get("source_path") or "")
    source_text = source_text_by_path.get(source_path, "")
    summary = re.search(rf"{re.escape(group)}包括：(.+?)。", source_text)
    if summary:
        fields = [value.strip() for value in summary.group(1).split("、") if value.strip()]
        if len(fields) >= 2:
            return _claim(
                "C1",
                "DIRECT",
                "SQ1",
                f"{group}包括：{'、'.join(dict.fromkeys(fields))}。",
                [preferred["evidence_id"]],
                raw_evidence_text=summary.group(0),
            )
    pairs = [
        (int(column), value.strip())
        for column, value in re.findall(r"列(\d+)：([^|\r\n]*)", source_text)
    ]
    group_columns = sorted(column for column, value in pairs if value == group)
    if not group_columns:
        return None
    start = group_columns[0]
    next_group = min(
        (column for column, value in pairs if column > start and "专业设计参数" in value),
        default=max((column for column, _ in pairs), default=start + 1) + 1,
    )
    excluded = {
        group,
        "学校建筑产品线设计指标库",
        "",
        "设计参数查询范围设置/平均值",
        "设计参数总体标准差【筛选后计算值自动更新】",
        "设计参数范围值【筛选后计算值自动更新】",
        "样本个数（个）【筛选后计算值自动更新】",
    }
    fields = []
    for column in range(start, next_group):
        values = [value for item_column, value in pairs if item_column == column]
        field = next(
            (
                value
                for value in values
                if value not in excluded
                and not value.startswith("#")
                and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?", value)
                and not value.endswith("个样本")
            ),
            None,
        )
        if field and field not in fields:
            fields.append(field)
    if len(fields) < 2:
        return None
    return _claim(
        "C1",
        "DIRECT",
        "SQ1",
        f"{group}包括：{'、'.join(fields)}。",
        [preferred["evidence_id"]],
        raw_evidence_text=source_text,
    )


def _structured_claims(bundle: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if bundle["query_plan"].get("query_type") not in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"}:
        return []
    if not rows:
        if bundle.get("structured_evidence_complete") is False:
            return []
        xlsx_field_claim = _xlsx_field_claim(bundle)
        if xlsx_field_claim is not None:
            return [xlsx_field_claim]
        direct = [item for item in bundle["verified_evidence"] if item.get("table_id") or (item.get("location") or {}).get("table")]
        if not direct:
            return []
        evidence = direct[0]
        counts = _table_counts(evidence["text"])
        if not counts:
            return []
        detail = "；".join(f"{name}{count}条" for name, count in counts.items())
        return [_claim("C1", "DIRECT", "SQ1", f"表中可核查的专业条目统计为：{detail}。", [evidence["evidence_id"]], raw_evidence_text=evidence["text"])]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = str(row.get("professional") or "").strip()
        if group:
            groups.setdefault(group, []).append(row)
    if not groups:
        return []
    bundle_id = str(rows[0]["bundle_evidence_id"])
    all_rows = [row["row_number"] for row in rows]
    raw_text = f"{len(rows)}条结构化明细；来源行：{','.join(map(str, all_rows))}"
    claims = [_claim("C1", "DIRECT", "SQ1", f"该清单按专业类别列示，共包含{len(groups)}个类别。", [bundle_id], raw_evidence_text=raw_text, source_rows=all_rows, source_row_ids=[row["row_id"] for row in rows])]
    for index, (group, group_rows) in enumerate(groups.items(), start=2):
        row_numbers = [row["row_number"] for row in group_rows]
        claims.append(_claim(f"C{index}", "DIRECT", "SQ2", f"{group}：{len(group_rows)}条。", [bundle_id], raw_evidence_text=f"{group}来源行：{','.join(map(str, row_numbers))}", source_rows=row_numbers, source_row_ids=[row["row_id"] for row in group_rows]))
    total_index = len(claims) + 1
    claims.append(_claim(f"C{total_index}", "DIRECT", "SQ2", f"合计：{len(rows)}条。", [bundle_id], raw_evidence_text=raw_text, source_rows=all_rows, source_row_ids=[row["row_id"] for row in rows]))
    asks_benefit = any(marker in str(bundle.get("question") or "") for marker in ("增加效益", "增加收益", "增加利润", "提高利润", "提升利润", "增效", "收益"))
    if asks_benefit:
        benefit_markers = ("增加效益", "增加收益", "增加利润", "提高利润", "提高效益", "提升利润", "提高收益")
        benefit_rows = [
            row
            for row in rows
            if any(
                marker in str(cell.get("normalized_value") or cell.get("raw_value") or "")
                for cell in row.get("cells", [])
                if cell.get("normalized_column_name") == "价值创造分析"
                for marker in benefit_markers
            )
        ]
        if benefit_rows:
            claims.append(_claim(f"C{len(claims)+1}", "DIRECT", "SQ3", f"按“价值创造分析”中包含增效、收益或利润表述统计，共{len(benefit_rows)}条。", [bundle_id], raw_evidence_text=f"增效/收益/利润标记来源行：{','.join(str(row['row_number']) for row in benefit_rows)}", source_rows=[row["row_number"] for row in benefit_rows], source_row_ids=[row["row_id"] for row in benefit_rows]))
            return claims
        return claims
    if not asks_benefit:
        return claims
    profit_field = any("利润" in str(cell.get("normalized_column_name") or cell.get("column_name") or "") for row in rows for cell in row.get("cells", []))
    if not profit_field:
        claims.append(_claim(f"C{len(claims)+1}", "LIMITATION", "SQ3", "当前表格没有可逐行验证的利润字段，无法按“利润大于0”的口径统计增加效益条数。", [bundle_id], raw_evidence_text="No reliable profit column exists in the structured table rows.", source_rows=all_rows, source_row_ids=[row["row_id"] for row in rows]))
        return claims
    positive = [row for row in rows if row.get("profit_numeric") is not None and float(row["profit_numeric"]) > 0]
    unknown = [row for row in rows if row.get("profit_numeric") is None]
    profit_index = len(claims) + 1
    claims.append(_claim(f"C{profit_index}", "DIRECT", "SQ3", f"按“利润大于0”口径，当前可确认的正数利润记录为{len(positive)}条。", [bundle_id], raw_evidence_text=f"利润>0来源行：{','.join(str(row['row_number']) for row in positive)}", source_rows=[row["row_number"] for row in positive], source_row_ids=[row["row_id"] for row in positive]))
    if unknown:
        claims.append(_claim(f"C{len(claims)+1}", "LIMITATION", "SQ3", f"另有{len(unknown)}条记录的利润字段为空或未判定，不能将其解释为无效益。", [bundle_id], raw_evidence_text=f"利润未判定来源行：{','.join(str(row['row_number']) for row in unknown)}", source_rows=[row["row_number"] for row in unknown], source_row_ids=[row["row_id"] for row in unknown]))
    return claims


def _structured_incomplete_claim(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = next((item for item in bundle["verified_evidence"] if (item.get("location") or {}).get("table") is not None), None)
    if evidence is None:
        return []
    return [_claim("C1", "LIMITATION", "SQ1", "已定位到结构化表格，但当前运行时未保留可回查的完整行级明细，不能安全输出分专业或汇总统计。", [evidence["evidence_id"]], raw_evidence_text="Structured source artifact is incomplete for the current evidence path.")]


def _table_counts(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for match in re.finditer(r"(建筑|结构|给排水|暖通|电气)\s*\|", text):
        values[match.group(1)] = values.get(match.group(1), 0) + 1
    return values


def _answered(bundle: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    return _answer(bundle, "ANSWERED", claims, limitations=[])


def _partial_answer(bundle: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    answered_subquestions = {claim["subquestion_id"] for claim in claims}
    limitations = [f"{item.get('subquestion', item['subquestion_id'])}：证据不足。" for item in bundle["coverage_map"] if item["coverage_status"] == "EVIDENCE_INSUFFICIENT" and item["subquestion_id"] not in answered_subquestions]
    for index, limitation in enumerate(limitations, start=len(claims) + 1):
        evidence_ids = [item["evidence_id"] for item in (bundle["verified_evidence"] or bundle["supporting_evidence"])[:1]]
        claims.append(_claim(f"C{index}", "INSUFFICIENT", "SQ3", limitation, evidence_ids, raw_evidence_text=limitation))
    # The limitation is already a cited claim; rendering it twice would make the
    # user-facing answer look like two independent findings.
    return _answer(bundle, "PARTIAL_ANSWER", claims, limitations=[])


def _conflict_answer(bundle: dict[str, Any]) -> dict[str, Any]:
    conflicting = bundle["conflicting_evidence"][:5]
    claims = [_claim(
        "C1",
        "LIMITATION",
        "SQ1",
        "结论：当前可核查资料对同一问题给出了不一致的事实口径，不能自动确定唯一答案。",
        [item["evidence_id"] for item in conflicting],
        raw_evidence_text="同范围、同年度、同指标的候选证据存在冲突。",
    )]
    by_text: dict[str, dict[str, Any]] = {}
    for evidence in conflicting:
        raw = _local_excerpt(evidence["text"], bundle["question"])
        text = _render_conflict_claim(raw)
        if not text:
            continue
        if text in by_text:
            by_text[text]["evidence_ids"].append(evidence["evidence_id"])
            by_text[text]["raw_evidence_text"] += "\n" + raw
            continue
        claim = _claim(f"C{len(claims)+1}", "CONFLICT", "SQ1", text, [evidence["evidence_id"]], raw_evidence_text=raw)
        claims.append(claim)
        by_text[text] = claim
    return _answer(bundle, "CONFLICTING_ANSWER", claims, limitations=[])


def _refusal(bundle: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    prefix = "" if message.startswith("结论：") else "结论："
    return _answer(bundle, status, [], limitations=[prefix + message])


def _answer(bundle: dict[str, Any], status: str, claims: list[dict[str, Any]], limitations: list[str]) -> dict[str, Any]:
    citations = []
    for claim in claims:
        citation_ids = []
        for evidence_id in claim["evidence_ids"]:
            evidence = next((item for item in bundle["candidate_evidence"] if item["evidence_id"] == evidence_id), None)
            if evidence is None:
                continue
            citation_id = f"S{len(citations)+1}"
            citations.append(_citation(citation_id, evidence, claim.get("source_rows"), claim.get("source_row_ids")))
            citation_ids.append(citation_id)
        claim["citation_ids"] = citation_ids
    lines = []
    for index, claim in enumerate(claims):
        rendered = claim["rendered_claim_text"]
        if index == 0 and status != "CONFLICTING_ANSWER" and not rendered.startswith("结论："):
            rendered = "结论：" + rendered
        lines.append(rendered + (" " + "".join(f"[{item}]" for item in claim["citation_ids"]) if claim["citation_ids"] else ""))
    lines.extend(limitations)
    answer = {"answer_id": str(uuid.uuid4()), "query_id": bundle["query_id"], "answer_status": status, "answer_text": "\n".join(lines) if lines else limitations[0] if limitations else "", "claims": claims, "claim_evidence_map": [{"claim_id": claim["claim_id"], "evidence_ids": claim["evidence_ids"], "citation_ids": claim["citation_ids"]} for claim in claims], "citations": citations, "covered_subquestions": [item["subquestion_id"] for item in bundle["coverage_map"] if item["coverage_status"] == "COVERED"], "uncovered_subquestions": [item["subquestion_id"] for item in bundle["coverage_map"] if item["coverage_status"] in {"NOT_COVERED", "EVIDENCE_INSUFFICIENT"}], "conflicts": bundle["conflicting_evidence"], "limitations": limitations, "source_scope_status": bundle["bundle_status"] == "SOURCE_SCOPE_MISSING", "lineage_status": bundle["bundle_status"] == "LINEAGE_BLOCKED", "generation_mode": "DETERMINISTIC_VERIFIED", "validation_status": "PENDING", "answer_trace": {"bundle_status": bundle["bundle_status"], "gold_runtime_injection": 0}}
    validation = validate(answer, bundle)
    answer["validation_status"] = "VALID" if validation["valid"] else "ANSWER_VALIDATION_FAILED"
    answer["answer_trace"]["validation_errors"] = validation["validation_errors"]
    return answer


def _claim(claim_id: str, claim_type: str, subquestion_id: str, text: str, evidence_ids: list[str], *, raw_evidence_text: str = "", source_rows: list[int] | None = None, source_row_ids: list[str] | None = None) -> dict[str, Any]:
    return {"claim_id": claim_id, "claim_text": text, "rendered_claim_text": text, "raw_evidence_text": raw_evidence_text, "claim_type": claim_type, "subquestion_id": subquestion_id, "support_status": claim_type, "evidence_ids": evidence_ids, "source_rows": source_rows or [], "source_row_ids": source_row_ids or [], "citation_ids": []}


def _citation(citation_id: str, evidence: dict[str, Any], source_rows: list[int] | None = None, source_row_ids: list[str] | None = None) -> dict[str, Any]:
    location = dict(evidence.get("location") or {})
    if source_rows:
        location.update({"row_start": min(source_rows), "row_end": max(source_rows), "source_row_numbers": source_rows, "source_row_ids": source_row_ids or []})
    return {"citation_id": citation_id, "evidence_id": evidence["evidence_id"], "document_id": evidence.get("document_id"), "source_path": evidence.get("source_path"), "file_name": evidence.get("file_name"), "location": location, "page": location.get("page"), "heading_path": evidence.get("heading_path"), "sheet": location.get("sheet_name"), "table": location.get("table"), "row": location.get("row_start") or location.get("row"), "column": location.get("column")}


def _short_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())[:360]


def _clean_display(text: str) -> str:
    value = re.sub(r"(?:[\u4e00-\u9fff]{2,6}\s+){1,2}20\d{2}\s*-\s*\d{1,2}\s*-\s*\d{1,2}\s+\d{1,2}:\d{2}", "", text)
    value = re.sub(r"\s+", " ", value).replace("�", "")
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"(?:-\s*\d+\s*-\s*)", "", value)
    return value.strip(" |；;")


def _render_direct_claims(raw: str, question: str) -> list[str]:
    text = _clean_display(raw)
    table_match = re.search(r"比选项：\s*([^|]+)\|\s*列5：\s*([^|]+)", text)
    if table_match:
        return [f"结论：可采用两种方案比选，方案一为{table_match.group(1).strip()}；方案二为{table_match.group(2).strip()}。"]
    if any(marker in question for marker in ("计算", "计算方式", "怎么算")):
        formula = re.search(r"(项目设计创效经济效益额)\s*=\s*(.+?)(?=(?:\d+[）)]\s*设计创效率|设计创效率|附则|$))", text)
        if formula:
            return [f"结论：{formula.group(1)} = {formula.group(2).strip(' 。')}。"]
    task_book = re.search(r"设计任务书(?:编制)?[^。；]{0,100}?(?:包含|包括)(.+?)(?:等内容|。)", text)
    if task_book:
        return [f"结论：设计任务书包含{task_book.group(1).strip(' ：，、')}等内容。"]
    headings = _evidence_headings(text)
    if _asks_for_structure(question) and headings:
        subject = _summary_subject(question, text)
        return [f"结论：{subject}主要包括{'、'.join(headings)}。"]
    sentence = _best_sentence(text, question)
    return [f"结论：{_sentence_end(sentence)}"]


def _risk_table_claims(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    question = bundle["question"]
    focused_risk_question = "风险" in question and any(marker in question for marker in ("影响", "建议", "化解", "措施"))
    if not focused_risk_question and not any(marker in question for marker in ("风险应对", "应对措施", "风险措施", "风险化解")):
        return []
    for evidence in bundle["verified_evidence"]:
        rows = _risk_table_rows(evidence["text"])
        if not rows:
            continue
        rows = _select_risk_rows(rows, question)
        lines = [f"结论：表中列出{len(rows)}项设计风险及对应策略、措施。"]
        for row in rows:
            if row.get("impact") or row.get("mitigation"):
                lines.append(f"{row['number']}. 风险：{row['risk']}；影响：{row.get('impact', '')}；化解建议：{row.get('mitigation', '')}")
            else:
                lines.append(f"{row['number']}. 风险：{row['risk']}；策略：{row['strategy']}；措施：{row['measures']}")
        source_rows = [int(row["number"]) for row in rows if str(row.get("number", "")).isdigit()]
        return [_claim("C1", "DIRECT", "SQ1", "\n".join(lines), [evidence["evidence_id"]], raw_evidence_text=evidence["text"], source_rows=source_rows)]
    return []


def _select_risk_rows(rows: list[dict[str, str]], question: str) -> list[dict[str, str]]:
    """Keep all rows for broad questions; isolate the strongest row for focused ones."""
    terms = [term for term in query_terms(question) if len(term) >= 2]
    if not terms:
        return rows
    scored = [
        (sum(term in _table_text(" ".join(row.values())) for term in terms), row)
        for row in rows
    ]
    best = max(score for score, _ in scored)
    selected = [row for score, row in scored if score == best]
    return selected if best >= 2 and len(selected) < len(rows) else rows


def _risk_table_rows(text: str) -> list[dict[str, str]]:
    if not all(header in text for header in ("风险描述", "应对策略", "应对措施")):
        return _pipe_risk_table_rows(text)
    lines = [re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", line.strip()) for line in text.splitlines()]
    start = next((index for index, line in enumerate(lines) if "风险描述" in line), None)
    if start is None:
        return []
    body = "\n".join(line for line in lines[start + 1:] if line)
    markers = list(re.finditer(r"(?m)^\s*(\d+)\s*$", body))
    rows: list[dict[str, str]] = []
    for index, marker in enumerate(markers):
        block = body[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(body)].strip()
        strategy = re.search(r"(风险(?:规避|化解|转移)(?:、\s*风险(?:规避|化解|转移))*)", block)
        if not strategy:
            continue
        risk = _table_text(block[:strategy.start()]).strip("；; ")
        measures = _table_text(block[strategy.end():]).strip("；; ")
        if risk and measures:
            rows.append({"number": marker.group(1), "risk": risk, "strategy": _table_text(strategy.group(1)), "measures": measures[:360]})
    return rows[:6]


def _pipe_risk_table_rows(text: str) -> list[dict[str, str]]:
    """Parse row-preserving risk tables whose headers are risk/impact/mitigation."""
    rows = []
    for line in text.splitlines():
        cells = [re.sub(r"\s+", "", part) for part in line.strip().strip("|").split("|")]
        if len(cells) < 7 or not re.fullmatch(r"\d+", cells[0]):
            continue
        risk, impact, mitigation = cells[3], cells[5], cells[6]
        if risk and (impact or mitigation):
            rows.append({"number": cells[0], "risk": risk, "impact": impact, "mitigation": mitigation})
    return rows[:20]


def _table_text(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("；", "；")


def _role_claims(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    question = bundle["question"]
    if not any(marker in question for marker in ("由谁组织", "谁组织", "谁牵头", "谁负责", "谁参与", "谁参加", "参与人员")):
        return []
    subject = _role_subject(question)
    candidates = [item for item in bundle["verified_evidence"] if _role_fact_relevance(item["text"], question) > 0]
    if not candidates:
        return []
    lead = max(candidates, key=lambda item: (_role_fact_relevance(item["text"], question), -int(item.get("candidate_rank") or 10**6)))
    primary = _role_primary_text(lead["text"], subject)
    if not primary:
        return []
    claims = [_claim("C1", "DIRECT", "SQ1", f"结论：{_sentence_end(primary)}", [lead["evidence_id"]], raw_evidence_text=lead["text"])]
    lead_page = (lead.get("location") or {}).get("page")
    continuation = next((item for item in candidates if item.get("document_id") == lead.get("document_id") and isinstance(lead_page, int) and (item.get("location") or {}).get("page") == lead_page + 1), None)
    if continuation:
        text = _role_continuation_text(continuation["text"])
        if text:
            claims.append(_claim("C2", "DIRECT", "SQ1", f"补充：{_sentence_end(text)}", [continuation["evidence_id"]], raw_evidence_text=continuation["text"]))
    return claims


def _role_subject(question: str) -> str:
    return re.split(r"(?:由谁组织|谁组织|谁牵头|谁负责|谁参与|谁参加|参与人员)", question, maxsplit=1)[0].strip("，、？?是 ")


def _role_primary_text(text: str, subject: str) -> str | None:
    value = _clean_display(text)
    if subject:
        match = re.search(re.escape(subject) + r"[^。；]{0,180}?(?:参与|参加)", value)
        if match:
            statement = re.sub(re.escape(subject) + r"\s*\d+\s*[）).]?\s*", subject, match.group(0))
            return re.sub(r"^" + re.escape(subject) + r"\s*" + re.escape(subject), subject, statement)
    return None


def _role_continuation_text(text: str) -> str | None:
    value = _clean_display(text)
    match = re.search(r"机构负责[^。；]{0,180}?(?:把关|负责)", value)
    return match.group(0) if match else None


def _same_document_facet_claim(bundle: dict[str, Any]) -> dict[str, Any] | None:
    """Join consecutive, verified section headings from one document only."""
    question = bundle["question"]
    if not _asks_for_structure(question) or any(item.get("exact_core_phrase_matches") for item in bundle["verified_evidence"]):
        return None
    groups: dict[tuple[str, str], list[tuple[str, str, dict[str, Any]]]] = {}
    for evidence in bundle["verified_evidence"]:
        for number, heading in _numbered_headings(evidence["text"]):
            parent = number.rsplit(".", 1)[0]
            groups.setdefault((str(evidence.get("document_id")), parent), []).append((number, heading, evidence))
    candidates = []
    for entries in groups.values():
        unique: list[tuple[str, str, dict[str, Any]]] = []
        seen = set()
        for number, heading, evidence in sorted(entries, key=lambda item: (_number_key(item[0]), int(item[2].get("candidate_rank") or 10**6))):
            if heading not in seen:
                unique.append((number, heading, evidence))
                seen.add(heading)
        if len(unique) >= 2:
            candidates.append(unique)
    if not candidates:
        return None
    selected = max(candidates, key=lambda entries: (len(entries), -min(int(item[2].get("candidate_rank") or 10**6) for item in entries)))
    evidence_ids = list(dict.fromkeys(item[2]["evidence_id"] for item in selected))
    labels = [item[1] for item in selected]
    source_text = "\n".join(item[2]["text"] for item in selected)
    return _claim("C1", "DIRECT", "SQ1", f"结论：{_summary_subject(question, source_text)}主要包括{'、'.join(labels)}。", evidence_ids, raw_evidence_text=source_text)


def _number_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _exact_phrase_sentence(text: str, phrases: list[str]) -> str | None:
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = r"\s*".join(re.escape(char) for char in phrase)
        match = re.search(rf"(?:^|[。；\n])\s*({pattern}\s*(?:[:：]|由|应|需|包括|是).*?)(?=[。；]|$)", text, flags=re.DOTALL)
        if match:
            return match.group(1)
    return None


def _sentence_end(text: str) -> str:
    return text if text.endswith(("。", "！", "？", "；")) else text + "。"


def _numbered_headings(text: str) -> list[tuple[str, str]]:
    pattern = r"(?:^|\s)(\d+(?:\.\d+)+)\s+([^\d。；]{2,32}?(?:评估|审查|分析|管理|策划|要求|内容|要点))"
    return [(number, re.sub(r"\s+", "", heading).strip("：、")) for number, heading in re.findall(pattern, text)]


def _evidence_headings(text: str) -> list[str]:
    # Prefer dotted section numbers such as 3.1 / 3.2.  They are the
    # actionable children of a parent chapter (for example, "3 设计评估").
    matches = [heading for _, heading in _numbered_headings(text)]
    # Chinese-numbered and bulleted source lists commonly use a short label
    # followed by a colon. Keep the label only; the explanatory paragraph is
    # available through the citation and must not become answer text.
    matches.extend(re.findall(r"(?:^|\s)(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)]|[-*•])\s*([^：:。；]{2,32})(?=\s*[：:])", text))
    result: list[str] = []
    for value in matches:
        heading = re.sub(r"\s+", "", value).strip("：、")
        if heading and heading not in result:
            result.append(heading)
    return result[:6]


def _asks_for_structure(question: str) -> bool:
    return any(marker in question for marker in ("哪些", "方面", "包括", "包含", "内容", "要点", "评估"))


def _summary_subject(question: str, text: str) -> str:
    for value in ("设计评估", "设计审查", "方案比选", "设计任务书", "设计管理"):
        if value in question or value in text:
            return value
    return "相关工作"


def _best_sentence(text: str, question: str) -> str:
    parts = [item.strip() for item in re.split(r"(?<=[。；！？])", text) if item.strip()]
    terms = [term for term in query_terms(question) if len(term) >= 2]
    if parts:
        best = max(parts, key=lambda item: (sum(term in item for term in terms), -len(item)))
        return _short_text(best)[:220]
    return _short_text(text)[:220]


def _render_direct_claim(raw: str, question: str) -> str:
    """Compatibility helper for callers that need one rendered statement."""
    return _render_direct_claims(raw, question)[0]


def _render_conflict_claim(raw: str) -> str | None:
    text = _clean_display(raw)
    metric = re.search(r"(?:设计)?创效金额\s*(?:约为?|为)?\s*\d[\d,.]*\s*(?:亿|万)元", text)
    if metric:
        return metric.group(0) + "。"
    return None


def _claim_relevance(source_text: str, excerpt: str, question: str) -> int:
    score = sum(term in excerpt for term in query_terms(question))
    if any(marker in question for marker in ("包含", "包括", "哪些内容", "主要内容")):
        content_markers = ("包含", "包括", "主要内容")
        score += 3 * any(marker in excerpt for marker in content_markers)
        subject_terms = [term for term in query_terms(question) if term not in content_markers]
        score += 5 * any(any(abs(match.start() - source_text.find(marker)) <= 240 for match in re.finditer(re.escape(term), source_text) for marker in content_markers if source_text.find(marker) >= 0) for term in subject_terms)
    score += _role_fact_relevance(excerpt, question)
    return score


def _role_fact_relevance(excerpt: str, question: str) -> int:
    asks_organization = any(marker in question for marker in ("由谁组织", "谁组织", "谁牵头", "谁负责"))
    asks_participation = any(marker in question for marker in ("谁参与", "谁参加", "参与人员"))
    if not (asks_organization or asks_participation):
        return 0
    score = 0
    if any(marker in excerpt for marker in ("组织", "牵头", "负责", "主持")):
        score += 4
    if any(marker in excerpt for marker in ("参与", "参加")):
        score += 4
    subject = re.split(r"(?:由谁组织|谁组织|谁牵头|谁负责|谁参与|谁参加|参与人员)", question, maxsplit=1)[0].strip("，、？?是 ")
    if len(subject) >= 3 and subject in excerpt:
        score += 8
        if re.search(re.escape(subject) + r"\s*(?:由|牵头|组织|负责|主持)", excerpt):
            score += 8
    return score


def _local_excerpt(text: str, question: str) -> str:
    """Return one source-local answer window without adding or paraphrasing facts."""
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    terms = {term for term in query_terms(question) if len(term) >= 2}
    if any(marker in question for marker in ("包含", "包括", "哪些内容", "主要内容")):
        terms.update(("包含", "包括", "主要内容"))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", question):
        terms.update(phrase[start:start + width] for width in range(min(8, len(phrase)), 1, -1) for start in range(len(phrase) - width + 1))
    terms = sorted(terms, key=len, reverse=True)
    matches = [(match.start(), match.end(), term) for term in terms for match in re.finditer(re.escape(term), normalized)]
    if not matches:
        return _short_text(normalized)
    sentence_marks = ("\u3002", "\uff1b", "\uff01", "\uff1f", "\n")

    def window(start: int, end: int) -> str:
        left = max(normalized.rfind(mark, 0, start) for mark in sentence_marks) + 1
        right_positions = [position for mark in sentence_marks if (position := normalized.find(mark, end)) >= 0]
        right = (min(right_positions) + 1) if right_positions else len(normalized)
        excerpt = _short_text(normalized[left:right])
        return excerpt if excerpt and len(excerpt) <= 380 else _short_text(normalized[max(0, start - 180): min(len(normalized), end + 300)])

    windows = [(window(start, end), start) for start, end, _ in matches]
    windows.extend((_short_text(normalized[max(0, start - 220): min(len(normalized), end + 300)]), start) for start, end, _ in matches)
    return max(windows, key=lambda item: (sum(term in item[0] for term in terms), -len(item[0]), -item[1]))[0]
