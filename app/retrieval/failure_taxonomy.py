"""T08 - 统一失败分类系统。

把一次问答的结果映射到明确的失败阶段与错误码，替代"没有找到可靠资料"。

设计原则：
    1. 只依据运行时产生的状态字段（bundle_status / answer_status / 候选数量 /
       校验结果）判定，禁止依据问题字符串做特例判断；
    2. 分类不了的一律落到 UNKNOWN，不允许猜测；
    3. 一个失败可以同时带多个候选阶段，按证据强度排序，主因为第一个。
"""

from __future__ import annotations

from typing import Any

# 一级阶段码
STAGES: dict[str, str] = {
    "01": "SOURCE",
    "02": "PARSE",
    "03": "STRUCTURE",
    "04": "CHUNK",
    "05": "METADATA",
    "06": "INDEX",
    "07": "RECALL",
    "08": "RERANK",
    "09": "SCOPE",
    "10": "EVIDENCE",
    "11": "ANSWER",
    "12": "CITATION",
    "13": "FEEDBACK",
}

# 核心错误码 -> (阶段码, 中文说明)
CODE_TABLE: dict[str, tuple[str, str]] = {
    "SOURCE_MISSING": ("01", "答案对应来源尚未进入来源库或文件不可读"),
    "SOURCE_DISABLED": ("01", "来源已停用或未完成索引"),
    "SOURCE_VERSION_ERROR": ("01", "来源版本关系错误，历史版本或失效版本参与检索"),
    "SOURCE_SCOPE_ERROR": ("01", "来源未纳入当前检索范围"),
    "SOURCE_BODY_MISSING": ("01", "来源名称已入库，但没有形成可用正文"),
    "PARSE_FAILED": ("02", "文件解析失败或正文乱码"),
    "OCR_FAILED": ("02", "扫描件未完成 OCR，未形成可用正文"),
    "STRUCTURE_LOST": ("03", "文档结构未恢复，缺少章节或标题上下文"),
    "TABLE_CONTEXT_LOST": ("03", "表格行失去表头与所属表格上下文"),
    "CHUNK_MISSING": ("04", "未形成可检索证据块"),
    "CHUNK_CONTEXT_MISSING": ("04", "证据块缺少父级上下文，语义不完整"),
    "METADATA_ERROR": ("05", "元数据缺失或错误，导致过滤或排序失准"),
    "INDEX_MISSING": ("06", "索引缺失，来源已解析但不可检索"),
    "RECALL_MISS": ("07", "正确资料存在，但未进入召回候选"),
    "RERANK_FAIL": ("08", "正确候选已召回，但排序未进入可用位次"),
    "SCOPE_MISMATCH": ("09", "候选证据与问题的明确范围不一致"),
    "SCOPE_MISMATCH_FALSE_REJECT": ("09", "正确证据已召回，但被范围判断错误拒绝"),
    "EVIDENCE_INSUFFICIENT": ("10", "候选资料存在，但正文不足以直接支持结论"),
    "EVIDENCE_CONFLICT": ("10", "同一问题存在尚未解决的冲突证据"),
    "EVIDENCE_FALSE_REJECT": ("10", "正确证据已召回且范围无冲突，但被证据核验拒绝"),
    "ANSWER_SYNTHESIS_FAIL": ("11", "证据充分但答案组合错误"),
    "ANSWER_MISSING_FACT": ("11", "答案遗漏必要事实"),
    "ANSWER_UNSUPPORTED_CLAIM": ("11", "答案包含证据不支持的论断"),
    "CITATION_VALIDATION_FAIL": ("12", "引用校验失败，主张与证据或出处不匹配"),
    "FEEDBACK_NOT_EFFECTIVE": ("13", "反馈已审核但未在普通问答中生效"),
    "NO_FAILURE": ("", "未失败"),
    "UNKNOWN": ("", "未能归因，需要人工复核"),
}

# bundle_status 到错误码的映射（仅使用状态字段，不涉及问题文本）
BUNDLE_STATUS_CODES: dict[str, str] = {
    "SOURCE_SCOPE_MISSING": "SCOPE_MISMATCH",
    "LINEAGE_BLOCKED": "SOURCE_VERSION_ERROR",
    "EVIDENCE_INSUFFICIENT": "EVIDENCE_INSUFFICIENT",
    "INSUFFICIENT_EVIDENCE": "EVIDENCE_INSUFFICIENT",
    "CONFLICTING_EVIDENCE": "EVIDENCE_CONFLICT",
    "NO_CANDIDATES": "RECALL_MISS",
}

ANSWER_STATUS_CODES: dict[str, str] = {
    "ANSWERED": "",
    "PARTIAL_ANSWER": "EVIDENCE_INSUFFICIENT",
    "INSUFFICIENT_EVIDENCE": "EVIDENCE_INSUFFICIENT",
    "CONFLICTING_ANSWER": "EVIDENCE_CONFLICT",
    "ANSWER_VALIDATION_FAILED": "CITATION_VALIDATION_FAIL",
    "SAFE_REFUSAL": "EVIDENCE_FALSE_REJECT",
}


def stage_name(code: str) -> str:
    entry = CODE_TABLE.get(code)
    return STAGES.get(entry[0], "") if entry else ""


def stage_code(code: str) -> str:
    entry = CODE_TABLE.get(code)
    return entry[0] if entry else ""


def describe(code: str) -> str:
    entry = CODE_TABLE.get(code)
    return entry[1] if entry else ""


def classify(
    *,
    answer_status: str | None,
    bundle_status: str | None = None,
    failure_reason: str | None = None,
    candidate_count: int = 0,
    verified_evidence_count: int = 0,
    claim_count: int = 0,
    citation_count: int = 0,
    validation_errors: list[str] | None = None,
    scope_mismatch_in_top: bool = False,
) -> dict[str, Any]:
    """把一次问答结果归类到失败阶段与错误码。

    判定顺序按链路先后：来源 -> 召回 -> 范围/证据 -> 答案 -> 引用。
    """
    candidates: list[str] = []

    status = (answer_status or "").strip()
    bundle = (bundle_status or "").strip()

    # 1. 引用校验：答案已生成但校验不通过
    if validation_errors:
        candidates.append("CITATION_VALIDATION_FAIL")

    # 2. 范围阻断：bundle 明确给出来源范围缺失
    if bundle in BUNDLE_STATUS_CODES:
        candidates.append(BUNDLE_STATUS_CODES[bundle])

    # 3. 召回层：完全没有候选
    if candidate_count <= 0:
        candidates.append("RECALL_MISS")

    # 4. 证据层：有候选但没有任何通过核验的证据
    if candidate_count > 0 and verified_evidence_count <= 0:
        if scope_mismatch_in_top:
            candidates.append("SCOPE_MISMATCH")
        else:
            candidates.append("EVIDENCE_INSUFFICIENT")

    # 5. 答案层
    if status in ANSWER_STATUS_CODES and ANSWER_STATUS_CODES[status]:
        candidates.append(ANSWER_STATUS_CODES[status])
    if verified_evidence_count > 0 and claim_count <= 0:
        candidates.append("ANSWER_SYNTHESIS_FAIL")

    # 6. 兜底
    if not candidates:
        if not status or status == "ANSWERED":
            return {
                "failure_stage": "",
                "failure_code": "NO_FAILURE",
                "failure_reason": "",
                "stage_code": "",
                "candidate_codes": [],
            }
        candidates.append("UNKNOWN")

    candidates = list(dict.fromkeys(candidates))
    primary = candidates[0]
    reason = describe(primary)
    if failure_reason:
        reason = f"{reason}；系统原始原因：{failure_reason}"

    return {
        "failure_stage": stage_name(primary),
        "failure_code": primary,
        "failure_reason": reason,
        "stage_code": stage_code(primary),
        "candidate_codes": candidates,
    }
