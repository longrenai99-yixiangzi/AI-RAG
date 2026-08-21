from __future__ import annotations

import re
from dataclasses import dataclass

from .domain import SearchHit
from .llm import LLMClient, LLMResponse


SOURCE_PATTERN = re.compile(r"\[(S\d+)\]")


@dataclass(slots=True)
class AnswerResult:
    answer: str
    citations: list[dict[str, object]]
    citation_valid: bool
    request_id: str | None
    elapsed_ms: int


def _location_label(location: dict[str, object]) -> str:
    if "page" in location:
        return f"第 {location['page']} 页"
    if "slide" in location:
        return f"第 {location['slide']} 页幻灯片"
    if "sheet" in location and "row" in location:
        return f"{location['sheet']}，第 {location['row']} 行"
    if "sheet" in location:
        return str(location["sheet"])
    if "line_start" in location:
        return f"第 {location['line_start']} 行起"
    if "paragraph" in location:
        return f"第 {location['paragraph']} 段起"
    if "table" in location:
        return f"表 {location['table']}"
    return ""


def _source_record(source_id: str, hit: SearchHit) -> dict[str, object]:
    chunk = hit.chunk
    return {
        "id": source_id,
        "file_name": chunk.file_name,
        "source_path": chunk.source_path,
        "heading_path": chunk.heading_path,
        "location": _location_label(chunk.location),
        "metadata": chunk.metadata,
        "retrieval": {
            "rrf_score": hit.score,
            "dense_rank": hit.dense_rank,
            "bm25_rank": hit.bm25_rank,
            "reranker_score": hit.reranker_score,
        },
        "excerpt": chunk.text[:900],
    }


def _context(hits: list[SearchHit]) -> tuple[str, dict[str, dict[str, object]]]:
    records: dict[str, dict[str, object]] = {}
    parts: list[str] = []
    total_characters = 0
    for index, hit in enumerate(hits, start=1):
        source_id = f"S{index}"
        record = _source_record(source_id, hit)
        snippet = hit.chunk.text[:1_600]
        heading = hit.chunk.heading_path or "未识别章节"
        location = record["location"] or "未定位"
        part = (
            f"[{source_id}]\n"
            f"文件：{hit.chunk.file_name}\n章节：{heading}\n位置：{location}\n"
            f"证据：\n{snippet}"
        )
        if total_characters + len(part) > 12_000:
            break
        parts.append(part)
        records[source_id] = record
        total_characters += len(part)
    return "\n\n---\n\n".join(parts), records


def validate_citations(answer: str, allowed_source_ids: set[str]) -> tuple[bool, list[str], list[str]]:
    used = SOURCE_PATTERN.findall(answer)
    invalid = sorted({source_id for source_id in used if source_id not in allowed_source_ids})
    return bool(used) and not invalid, used, invalid


SYSTEM_PROMPT = """你是“AI设计管理知识助手”。
只能依据下方提供的知识库证据回答。不得编造制度名称、条款号、项目事实或来源。
必须区分：已检索到的依据、基于依据的实施建议、以及证据不足之处。
不要把项目经验写成强制制度要求。若证据不足，请明确写“当前知识库未检索到足够依据”。
每一项重要结论后必须使用唯一允许的来源标记，例如 [S1]。不要创造其他标记。"""


def _answer_sections(intent: str) -> str:
    return {
        "FACT_LOOKUP": "【结论】\n【依据】\n【来源】",
        "POLICY_QUERY": "【管理要求】\n【具体规定】\n【适用范围】\n【来源】",
        "METHOD_GUIDANCE": "【结论】\n【主要做法】\n【实施建议】\n【案例参考】\n【来源】",
        "CASE_QUERY": "【项目/案例】\n【主要做法】\n【实施效果】\n【可借鉴点】\n【来源】",
        "COMPARISON": "【主要差异】\n【分析】\n【建议】\n【来源】",
    }.get(intent, "【结论】\n【依据】\n【实施建议】\n【来源】")


def generate_answer(
    question: str,
    hits: list[SearchHit],
    client: LLMClient,
    query_analysis: dict[str, object] | None = None,
) -> AnswerResult:
    context, records = _context(hits)
    if not context:
        return AnswerResult(
            answer="当前知识库未检索到足够依据。",
            citations=[],
            citation_valid=True,
            request_id=None,
            elapsed_ms=0,
        )
    intent = str((query_analysis or {}).get("intent", "GENERAL_RAG"))
    sections = _answer_sections(intent)
    user_prompt = f"问题：{question}\n\n问题类型：{intent}\n\n知识库证据：\n{context}\n\n请按以下结构回答：\n{sections}"
    response = client.complete(SYSTEM_PROMPT, user_prompt)
    valid, used, invalid = validate_citations(response.content, set(records))
    if not valid:
        repair_prompt = (
            f"{user_prompt}\n\n上一版回答的引用校验失败："
            f"{', '.join(f'[{item}]' for item in invalid) if invalid else '未使用任何来源标记'}。"
            "请重新回答，且只能使用证据中实际存在的 [S1] 至 [S8] 标记。"
        )
        response = client.complete(SYSTEM_PROMPT, repair_prompt)
        valid, used, _ = validate_citations(response.content, set(records))
    if not valid:
        return AnswerResult(
            answer="模型输出未能通过来源引用校验。请以下方检索证据为准，并重新提问或缩小问题范围。",
            citations=list(records.values()),
            citation_valid=False,
            request_id=response.request_id,
            elapsed_ms=response.elapsed_ms,
        )
    seen: set[str] = set()
    citations: list[dict[str, object]] = []
    for source_id in used:
        if source_id not in seen:
            seen.add(source_id)
            citations.append(records[source_id])
    return AnswerResult(
        answer=response.content,
        citations=citations,
        citation_valid=True,
        request_id=response.request_id,
        elapsed_ms=response.elapsed_ms,
    )
