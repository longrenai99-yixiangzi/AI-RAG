from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.answer_engine.answer_policy import AnswerPolicy
from app.answer_engine.evidence_selector import EvidenceBundle
from app.llm import LLMError

from .claim_validator import ClaimValidationResult, validate_claims
from .citation_renderer import CitationRenderResult, render_claim_citations
from .llm_provider import GenerationResult, LLMProvider
from .prompt_builder import build_prompt
from .response_schema import SchemaValidationResult, response_schema, schema_fields, validate_response


MAX_TOKENS = 4096


@dataclass(slots=True)
class GeneratedAnswer:
    status: str
    answer_text: str
    claims: list[dict[str, Any]] = field(default_factory=list)
    validation: ClaimValidationResult | None = None
    citation_render: CitationRenderResult | None = None
    request_id: str | None = None
    elapsed_ms: int = 0
    error: str | None = None
    evidence_roles: list[str] = field(default_factory=list)
    failure_category: str | None = None
    initial_failure_category: str | None = None
    protocol_category: str | None = None
    initial_protocol_category: str | None = None
    structure_valid: bool = False
    repair_triggered: bool = False
    repair_success: bool = False
    raw_llm_response: str | None = None
    parsed_response: dict[str, Any] | None = None
    repair_response: str | None = None
    error_events: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    initial_diagnostics: dict[str, Any] = field(default_factory=dict)
    repair_diagnostics: dict[str, Any] = field(default_factory=dict)


class ShadowAnswerGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self._last_repair_error_event: dict[str, Any] | None = None

    def generate(
        self,
        question: str,
        policy: AnswerPolicy,
        evidence: EvidenceBundle,
    ) -> GeneratedAnswer:
        roles = [item.document_role for item in evidence.items]
        if not evidence.items:
            return GeneratedAnswer(status="NO_EVIDENCE", answer_text="", evidence_roles=roles)
        if not self.provider.available:
            return GeneratedAnswer(
                status="LLM_ERROR",
                answer_text="",
                error=self.provider.last_error,
                evidence_roles=roles,
            )

        prompt = build_prompt(question, policy, evidence)
        result: GenerationResult | None = None
        error_events: list[dict[str, Any]] = []
        for attempt in range(3):
            started = time.perf_counter()
            try:
                result = self.provider.generate(
                    prompt.system_prompt,
                    prompt.user_prompt,
                    max_tokens=MAX_TOKENS,
                )
                break
            except LLMError as error:
                error_events.append(
                    _error_event(
                        phase="generation",
                        attempt=attempt + 1,
                        error=error,
                        provider=self.provider,
                        elapsed_ms=round((time.perf_counter() - started) * 1_000),
                        max_tokens=MAX_TOKENS,
                    )
                )
                if attempt == 2:
                    return GeneratedAnswer(
                        status="LLM_ERROR",
                        answer_text="",
                        error=f"{type(error).__name__}: {error}",
                        evidence_roles=roles,
                        error_events=error_events,
                        diagnostics=_diagnostics(getattr(self.provider, "last_diagnostics", {}), MAX_TOKENS),
                    )
        assert result is not None
        raw_response = result.content
        initial_diagnostics = _diagnostics(result.diagnostics, MAX_TOKENS, result.elapsed_ms)
        payload, parse_error = _parse_payload(raw_response)
        protocol_category = _parse_category(parse_error, raw_response, initial_diagnostics)
        if payload is not None:
            _normalize_claim_ids(payload, policy)
        schema_result = (
            validate_response(payload, policy, {item.source_id for item in evidence.items})
            if payload is not None
            else SchemaValidationResult(False, protocol_category or "B", [parse_error or "invalid JSON"])
        )
        claims = payload.get("claims", []) if isinstance(payload, dict) else []
        rendered = (
            render_claim_citations(payload, policy, evidence)
            if isinstance(payload, dict)
            else CitationRenderResult("", False, [parse_error or "invalid JSON"])
        )
        validation = validate_claims(rendered.answer_text, claims, evidence)
        initial_category = _failure_category(schema_result, rendered, validation)
        initial_status = _answer_status(schema_result, rendered, validation, payload)
        if initial_status in {"GENERATED", "NO_EVIDENCE"}:
            return _result(
                status=initial_status,
                payload=payload,
                claims=claims,
                rendered=rendered,
                validation=validation,
                result=result,
                roles=roles,
                raw_response=raw_response,
                error_events=error_events,
                protocol_category=_protocol_category(schema_result, protocol_category, parse_error),
                initial_protocol_category=_protocol_category(schema_result, protocol_category, parse_error),
                failure_category=None if initial_status == "GENERATED" else initial_category,
                initial_failure_category=initial_category,
                initial_diagnostics=initial_diagnostics,
            )

        self._last_repair_error_event = None
        repair = self._repair(question, policy, evidence, raw_response)
        if self._last_repair_error_event is not None:
            error_events.append(self._last_repair_error_event)
        if repair is None:
            return _result(
                status=_failure_status(schema_result, initial_status),
                payload=payload,
                claims=claims,
                rendered=rendered,
                validation=validation,
                result=result,
                roles=roles,
                raw_response=raw_response,
                error_events=error_events,
                protocol_category=_protocol_category(schema_result, protocol_category, parse_error),
                initial_protocol_category=_protocol_category(schema_result, protocol_category, parse_error),
                failure_category=initial_category,
                initial_failure_category=initial_category,
                repair_triggered=True,
                initial_diagnostics=initial_diagnostics,
            )

        repair_result, repair_payload, repair_raw = repair
        repair_diagnostics = _diagnostics(repair_result.diagnostics, MAX_TOKENS, repair_result.elapsed_ms)
        _normalize_claim_ids(repair_payload, policy)
        repaired_schema = validate_response(
            repair_payload,
            policy,
            {item.source_id for item in evidence.items},
        )
        repaired_claims = repair_payload.get("claims", [])
        repaired_render = render_claim_citations(repair_payload, policy, evidence)
        repaired_validation = validate_claims(
            repaired_render.answer_text,
            repaired_claims,
            evidence,
        )
        repaired_status = _answer_status(
            repaired_schema,
            repaired_render,
            repaired_validation,
            repair_payload,
        )
        return _result(
            status=repaired_status,
            payload=repair_payload,
            claims=repaired_claims,
            rendered=repaired_render,
            validation=repaired_validation,
            result=repair_result,
            roles=roles,
            raw_response=raw_response,
            error_events=error_events,
            protocol_category=_protocol_category(repaired_schema, None, None),
            initial_protocol_category=_protocol_category(schema_result, protocol_category, parse_error),
            failure_category=None if repaired_status in {"GENERATED", "NO_EVIDENCE"} else _failure_category(repaired_schema, repaired_render, repaired_validation),
            initial_failure_category=initial_category,
            repair_triggered=True,
            repair_success=repaired_status == "GENERATED",
            repair_response=repair_raw,
            initial_diagnostics=initial_diagnostics,
            repair_diagnostics=repair_diagnostics,
        )

    def _repair(
        self,
        question: str,
        policy: AnswerPolicy,
        evidence: EvidenceBundle,
        original: str,
    ) -> tuple[GenerationResult, dict[str, Any], str] | None:
        repair_system = (
            "你是受限 JSON Repair 工具。只修复 JSON、字段类型、Claim ID 和 section_map 映射。"
            "禁止新增事实、Evidence 或 Citation；只返回 Minimal Answer Schema JSON。"
        )
        repair_user = "\n".join(
            [
                f"原问题：{question}",
                "原始输出：",
                original,
                "允许的 Evidence ID：",
                ", ".join(item.source_id for item in evidence.items),
                "严格 Schema：",
                json.dumps(response_schema(policy), ensure_ascii=False, indent=2),
                "只返回修复后的 JSON；没有证据的回答使用空 section_map，并在 evidence_insufficient 中说明。",
            ]
        )
        started = time.perf_counter()
        try:
            result = self.provider.generate(
                repair_system,
                repair_user,
                temperature=0,
                max_tokens=MAX_TOKENS,
            )
        except LLMError as error:
            self._last_repair_error_event = _error_event(
                phase="repair",
                attempt=1,
                error=error,
                provider=self.provider,
                elapsed_ms=round((time.perf_counter() - started) * 1_000),
                max_tokens=MAX_TOKENS,
            )
            return None
        payload, _ = _parse_payload(result.content)
        return (result, payload, result.content) if isinstance(payload, dict) else None


def _result(
    *,
    status: str,
    payload: dict[str, Any] | None,
    claims: list[dict[str, Any]],
    rendered: CitationRenderResult,
    validation: ClaimValidationResult,
    result: GenerationResult,
    roles: list[str],
    raw_response: str,
    error_events: list[dict[str, Any]],
    protocol_category: str | None,
    initial_protocol_category: str | None,
    failure_category: str | None,
    initial_failure_category: str | None,
    repair_triggered: bool = False,
    repair_success: bool = False,
    repair_response: str | None = None,
    initial_diagnostics: dict[str, Any] | None = None,
    repair_diagnostics: dict[str, Any] | None = None,
) -> GeneratedAnswer:
    return GeneratedAnswer(
        status=status,
        answer_text=rendered.answer_text,
        claims=claims,
        validation=validation,
        citation_render=rendered,
        request_id=result.request_id,
        elapsed_ms=result.elapsed_ms,
        evidence_roles=roles,
        failure_category=failure_category,
        initial_failure_category=initial_failure_category,
        protocol_category=protocol_category,
        initial_protocol_category=initial_protocol_category,
        structure_valid=status != "STRUCTURE_INVALID",
        repair_triggered=repair_triggered,
        repair_success=repair_success,
        raw_llm_response=raw_response,
        parsed_response=payload,
        repair_response=repair_response,
        error_events=error_events,
        diagnostics=_diagnostics(result.diagnostics, MAX_TOKENS, result.elapsed_ms),
        initial_diagnostics=initial_diagnostics or {},
        repair_diagnostics=repair_diagnostics or {},
    )


def _answer_status(
    schema_result: SchemaValidationResult,
    rendered: CitationRenderResult,
    validation: ClaimValidationResult,
    payload: dict[str, Any] | None,
) -> str:
    if not schema_result.valid:
        return "PARTIAL_EVIDENCE" if schema_result.category == "F" else "STRUCTURE_INVALID"
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    if not claims or not rendered.visible_section_ids:
        return "NO_EVIDENCE"
    if not rendered.valid or not validation.valid:
        return "PARTIAL_EVIDENCE"
    insufficient = payload.get("evidence_insufficient", []) if isinstance(payload, dict) else []
    if any(isinstance(item, str) and item.strip() for item in insufficient):
        return "PARTIAL_EVIDENCE"
    return "GENERATED"


def _failure_status(schema_result: SchemaValidationResult, status: str) -> str:
    if not schema_result.valid and schema_result.category != "F":
        return "STRUCTURE_INVALID"
    return "PARTIAL_EVIDENCE" if status != "NO_EVIDENCE" else status


def _parse_payload(content: str) -> tuple[dict[str, Any] | None, str | None]:
    text = content.strip()
    fence = chr(96) * 3
    if text.startswith(fence) and text.endswith(fence):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit(fence, 1)[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error}"
    return (payload, None) if isinstance(payload, dict) else (None, "JSON root is not object")


def _normalize_claim_ids(payload: dict[str, Any], policy: AnswerPolicy) -> None:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            continue
        old = str(claim.get("claim_id") or "")
        candidate = old if re.fullmatch(r"C\d+", old) else f"C{index}"
        if candidate in used:
            candidate = f"C{index}"
        used.add(candidate)
        if old:
            mapping[old] = candidate
        claim["claim_id"] = candidate
    section_map = payload.get("section_map")
    if isinstance(section_map, dict):
        for field_name in schema_fields(policy):
            values = section_map.get(field_name)
            if isinstance(values, list):
                section_map[field_name] = [mapping.get(str(value), str(value)) for value in values]


def _failure_category(
    schema_result: SchemaValidationResult,
    rendered: CitationRenderResult,
    claim_result: ClaimValidationResult,
) -> str:
    if not schema_result.valid:
        return schema_result.category
    if claim_result.missing_evidence_claims:
        return "E"
    if claim_result.invalid_source_ids:
        return "F"
    if not rendered.valid or any("claim" in error for error in claim_result.errors):
        return "G"
    if claim_result.unsupported_claims:
        return "H"
    return "I"


def _parse_category(
    parse_error: str | None,
    raw_response: str,
    diagnostics: dict[str, Any],
) -> str | None:
    if not parse_error:
        return None
    if diagnostics.get("finish_reason") == "length" or "Unterminated" in parse_error:
        return "A"
    if not raw_response.rstrip().endswith(("}", "]")):
        return "A"
    return "B"


def _protocol_category(
    schema_result: SchemaValidationResult,
    parse_category: str | None,
    parse_error: str | None,
) -> str:
    if parse_error:
        return parse_category or "B"
    return "VALID" if schema_result.valid else schema_result.category


def _diagnostics(
    diagnostics: dict[str, Any] | None,
    max_tokens: int,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    source = diagnostics or {}
    return {
        "finish_reason": source.get("finish_reason"),
        "prompt_tokens": source.get("prompt_tokens"),
        "completion_tokens": source.get("completion_tokens"),
        "total_tokens": source.get("total_tokens"),
        "max_tokens": source.get("max_tokens", max_tokens),
        "response_length": source.get("response_length"),
        "elapsed_ms": source.get("elapsed_ms", elapsed_ms),
        "http_status": source.get("http_status"),
    }


def _error_event(
    *,
    phase: str,
    attempt: int,
    error: Exception,
    provider: LLMProvider,
    elapsed_ms: int,
    max_tokens: int,
) -> dict[str, Any]:
    diagnostics = _diagnostics(getattr(provider, "last_diagnostics", {}), max_tokens, elapsed_ms)
    cause = error.__cause__
    exception_type = type(cause).__name__ if cause is not None else type(error).__name__
    return {
        "phase": phase,
        "attempt": attempt,
        "exception_type": exception_type,
        "http_status": diagnostics["http_status"],
        "elapsed_ms": elapsed_ms,
        "error": str(error),
        **diagnostics,
    }
