from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any, Iterable

from app.bm25 import tokenize


COMMON_TERMS = {
    "设计",
    "项目",
    "管理",
    "问题",
    "哪些",
    "什么",
    "如何",
    "需要",
    "可以",
    "进行",
    "要求",
    "内容",
    "多少",
    "分别",
    "其中",
}


def search_atomic_evidence(
    query: str, records: Iterable[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    records = list(records)
    terms = query_terms(query)
    if not terms:
        return []
    token_sets = []
    query_phrases = phrases(query)
    for record in records:
        searchable = " ".join(str(record.get(field) or "") for field in ("text", "heading_path", "file_name", "source_path"))
        token_sets.append((searchable, set(_tokenize_cached(searchable))))
    document_frequency = {
        term: sum(term in tokens or (len(term) >= 3 and term in searchable) for searchable, tokens in token_sets)
        for term in terms
    }
    total_records = max(1, len(records))
    facets = query_facets(query)
    results: list[dict[str, Any]] = []
    for record, (searchable, record_terms) in zip(records, token_sets, strict=True):
        matched = sorted(
            {
                term
                for term in terms
                if term in record_terms or (len(term) >= 3 and term in searchable)
            },
            key=len,
            reverse=True,
        )
        if not matched:
            continue
        score = sum(math.log((total_records + 1) / (document_frequency[term] + 1)) + 1 for term in matched)
        identity_text = " ".join(str(record.get(field) or "") for field in ("file_name", "heading_path", "source_path"))
        identity_matches = [term for term in matched if term in identity_text]
        score += sum(math.log((total_records + 1) / (document_frequency[term] + 1)) for term in identity_matches)
        if query.strip() and query.strip().lower() in searchable.lower():
            score += 20
        record_text = str(record.get("text") or "")
        phrase_matches = [phrase for phrase in query_phrases if phrase.lower() in record_text.lower()]
        score += sum(2.0 for phrase in phrase_matches)
        if record_text.startswith("#"):
            score -= 5.0
        if record.get("file_type") == ".md" and any(marker in record_text for marker in ("file://", "[[")):
            score -= 4.0
        if len(record_text) >= 24 and not record_text.startswith("#"):
            score += 0.5
        normalized_searchable = _compact(searchable)
        normalized_text = _compact(record_text)
        year_matches = [year for year in facets["years"] if year in normalized_searchable]
        metric_matches = [term for term in facets["metrics"] if term in normalized_searchable]
        text_metric_matches = [term for term in facets["metrics"] if term in normalized_text]
        entity_matches = _maximal_matches(facets["entities"], identity_text)
        text_entity_matches = _maximal_matches(facets["entities"], record_text)
        cell_headers = " ".join(str(cell.get("header") or "") for cell in record.get("cells", []))
        field_matches = _maximal_matches(facets["fields"], f"{record_text} {cell_headers}")
        if facets["years"]:
            score += 3.0 * len(year_matches) - 2.0 * (len(facets["years"]) - len(year_matches))
        score += 1.5 * len(metric_matches)
        score += 2.0 * len(text_metric_matches)
        score += 2.0 * len(field_matches)
        score += 2.5 * len(entity_matches)
        score += 3.0 * len(text_entity_matches)
        if facets["metrics"] and not (metric_matches or text_metric_matches):
            score -= 1.5 * len(facets["metrics"])
        if facets["fields"] and not field_matches:
            score -= 1.5 * len(facets["fields"])
        results.append(
            {
                "score": round(score, 6),
                "matched_terms": matched,
                "identity_match_terms": [term for term in identity_matches if not term.isdigit()],
                "phrase_matches": phrase_matches,
                "year_matches": year_matches,
                "metric_matches": metric_matches,
                "text_metric_matches": text_metric_matches,
                "entity_matches": entity_matches,
                "text_entity_matches": text_entity_matches,
                "field_matches": field_matches,
                "facet_reasons": _facet_reasons(
                    facets,
                    year_matches,
                    metric_matches,
                    text_metric_matches,
                    entity_matches,
                    text_entity_matches,
                    field_matches,
                ),
                "record": record,
            }
        )
    return sorted(
        results,
        key=lambda item: (-item["score"], str(item["record"].get("evidence_id") or "")),
    )[:limit]


def query_terms(query: str) -> list[str]:
    return list(
        dict.fromkeys(
            term.lower()
            for term in tokenize(query)
            if len(term.strip()) > 1 and term.strip() not in COMMON_TERMS
        )
    )


def phrases(query: str) -> list[str]:
    tokens = [term for term in tokenize(query) if len(term.strip()) > 1 and term.strip() not in COMMON_TERMS]
    phrases = [term for term in tokens if len(term) >= 3]
    phrases.extend(
        tokens[index] + tokens[index + 1]
        for index in range(len(tokens) - 1)
        if len(tokens[index]) + len(tokens[index + 1]) >= 4
        and not tokens[index].isascii()
        and not tokens[index + 1].isascii()
    )
    return list(dict.fromkeys(phrases))


def query_facets(query: str) -> dict[str, list[str]]:
    years = list(dict.fromkeys(re.findall(r"20\d{2}", query)))
    metrics = [
        term
        for term in (
            "工期",
            "金额",
            "多少天",
            "数量",
            "专业",
            "效益",
            "创效",
            "利润",
            "比选",
            "方案",
            "督办",
            "责任状",
            "示范项目",
        )
        if term in query
    ]
    fields = [
        term
        for term in (
            "工期",
            "总工期",
            "设计工期",
            "金额",
            "创效金额",
            "利润",
            "数量",
            "上传数量",
            "专业",
            "方案",
            "比选",
            "督办",
            "责任状",
            "示范项目",
        )
        if term in query
    ]
    entities = []
    entity_pattern = re.compile(
        r"([\u3400-\u9fffA-Za-z0-9（）()·+\-]{2,32}(?:项目|中心|医院|馆|园|厂房|学校))"
    )
    for match in entity_pattern.finditer(query):
        candidate = match.group(1).strip("（）() ")
        candidate = re.sub(r"^20\d{2}年", "", candidate)
        if not candidate:
            continue
        if candidate.endswith("的") or candidate.startswith(("设计", "示范", "当前", "具体")):
            continue
        if candidate in {"项目", "设计中心", "公司中心"}:
            continue
        entities.append(candidate)
    return {
        "years": years,
        "metrics": list(dict.fromkeys(metrics)),
        "fields": list(dict.fromkeys(fields)),
        "entities": list(dict.fromkeys(entities)),
    }


def _maximal_matches(candidates: list[str], text: str) -> list[str]:
    matched = [candidate for candidate in candidates if candidate and candidate in text]
    selected: list[str] = []
    for candidate in sorted(set(matched), key=len, reverse=True):
        if not any(candidate in existing for existing in selected):
            selected.append(candidate)
    return selected


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _facet_reasons(
    facets: dict[str, list[str]],
    year_matches: list[str],
    metric_matches: list[str],
    text_metric_matches: list[str],
    entity_matches: list[str],
    text_entity_matches: list[str],
    field_matches: list[str],
) -> list[str]:
    reasons = []
    if year_matches:
        reasons.append("year_match")
    elif facets["years"]:
        reasons.append("year_missing")
    if metric_matches:
        reasons.append("metric_match")
    if text_metric_matches:
        reasons.append("metric_in_text")
    if entity_matches:
        reasons.append("entity_in_identity")
    if text_entity_matches:
        reasons.append("entity_in_text")
    if field_matches:
        reasons.append("field_match")
    return reasons


@lru_cache(maxsize=50_000)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    return tuple(tokenize(text))
