from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .database import IndexDatabase


GAP_STATUSES = {"NO_RETRIEVAL", "INSUFFICIENT_EVIDENCE", "CITATION_INVALID", "LLM_ERROR"}


def normalize_topic(analysis: dict[str, Any], question: str) -> str:
    filters = analysis.get("filters") or {}
    if filters:
        parts = [str(analysis.get("intent", "GENERAL_RAG"))]
        for key in sorted(filters):
            value = filters[key]
            if isinstance(value, list):
                value = ",".join(sorted(map(str, value)))
            parts.append(f"{key}={value}")
        return "|".join(parts)
    text = re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", " ", question.casefold())
    stop_words = {"什么", "哪些", "如何", "怎么", "请问", "能否", "有没有", "问题"}
    terms = [term for term in text.split() if term not in stop_words]
    return f"{analysis.get('intent', 'GENERAL_RAG')}|{' '.join(terms[:12])}".strip("|")


def classify_answer_status(
    *,
    hit_count: int,
    citation_valid: bool | None,
    answer: str | None,
    error: Exception | None = None,
) -> tuple[str, str | None]:
    if error is not None:
        return "LLM_ERROR", f"问答模型或生成链路失败：{type(error).__name__}"
    if not hit_count:
        return "NO_RETRIEVAL", "未召回任何候选片段"
    if citation_valid is False:
        return "CITATION_INVALID", "模型回答未通过来源引用校验"
    text = answer or ""
    if any(marker in text for marker in ("未检索到足够依据", "知识库未覆盖", "无法确定", "依据不足")):
        return "INSUFFICIENT_EVIDENCE", "回答明确表示证据不足"
    return "ANSWERED", None


class GrowthManager:
    def __init__(self, database: IndexDatabase, data_root: Path) -> None:
        self.database = database
        self.candidate_root = data_root / "growth" / "candidates"

    def record(
        self,
        *,
        question: str,
        retrieval: dict[str, Any],
        answer: str | None,
        citations: list[dict[str, Any]],
        citation_valid: bool | None,
        error: Exception | None = None,
    ) -> dict[str, Any]:
        analysis = retrieval.get("query_analysis") or {}
        status, reason = classify_answer_status(
            hit_count=int(retrieval.get("fused_hits", 0)),
            citation_valid=citation_valid,
            answer=answer,
            error=error,
        )
        normalized = normalize_topic(analysis, question)
        logged = self.database.record_query(
            query=question,
            analysis=analysis,
            retrieval_count=int(retrieval.get("fused_hits", 0)),
            answer_status=status,
            answer=answer,
            citations=citations,
            confidence=1.0 if status == "ANSWERED" else 0.0,
            normalized_topic=normalized if status in GAP_STATUSES else None,
            gap_reason=reason,
        )
        gap = logged.get("gap")
        candidate = None
        if gap:
            candidate = self._ensure_candidate(gap, question, analysis, reason, citations)
        return {
            "query_id": logged["query_id"],
            "answer_status": status,
            "gap": gap,
            "candidate": candidate,
        }

    def _ensure_candidate(
        self,
        gap: dict[str, Any],
        question: str,
        analysis: dict[str, Any],
        reason: str | None,
        citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        gap_id = str(gap["gap_id"])
        self.candidate_root.mkdir(parents=True, exist_ok=True)
        path = self.candidate_root / f"{gap_id}.md"
        if not path.exists():
            evidence = "\n".join(
                f"- [{item.get('id', 'S?')}] {item.get('file_name', '')} / "
                f"{item.get('heading_path', '')} / {item.get('location', '未定位')}"
                for item in citations
            ) or "- 当前没有可引用证据。"
            content = (
                "---\n"
                "type: knowledge_gap_candidate\n"
                f"gap_id: {gap_id}\n"
                "status: pending_review\n"
                "generated_by: rule_based_gap_capture\n"
                "formal_write: forbidden\n"
                "---\n\n"
                f"# 待审核知识候选：{question}\n\n"
                "## 缺口记录\n\n"
                f"- 问题：{question}\n"
                f"- 原因：{reason or '证据不足'}\n"
                f"- 意图：{analysis.get('intent', 'GENERAL_RAG')}\n"
                f"- 主题键：{gap.get('normalized_topic', '')}\n\n"
                "## 当前检索证据\n\n"
                f"{evidence}\n\n"
                "## 审核要求\n\n"
                "请回到原始文件核对事实、版本、适用范围和冲突；确认前不得写入正式知识或作为确定性结论。\n"
            )
            path.write_text(content, encoding="utf-8")
        return self.database.attach_growth_candidate(gap_id, str(path))
