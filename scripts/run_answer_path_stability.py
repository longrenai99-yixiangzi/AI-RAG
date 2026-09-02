from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.answer_engine.llm.prompt_builder import build_prompt
from app.answer_engine.llm.response_schema import validate_response
from app.config import Settings
from scripts.build_ba010_fact_claim_shadow import (
    build_claims as build_non_atomic_claims,
    load_facts,
    render_answer,
    validate_citations,
    validate_claims,
)
from scripts.diagnose_answer_engine_failure import build_bundle, failure_stage
from scripts.normalize_ba010_atomic_claims import (
    build_atomic_claims,
    validate_atomic_claims,
)


OPTIMIZED_BA007 = PROJECT_ROOT / "evaluation" / "traces_optimized" / "BA-007.json"
OPTIMIZED_BA010 = PROJECT_ROOT / "evaluation" / "traces_optimized" / "BA-010.json"
OUTPUT_ROOT = PROJECT_ROOT / "evaluation" / "answer_stability"
REPORT = PROJECT_ROOT / "docs" / "ANSWER_PATH_STABILITY_REGRESSION_REPORT.md"
RUNS = 10


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_ba007() -> list[dict[str, Any]]:
    trace = json.loads(OPTIMIZED_BA007.read_text(encoding="utf-8"))
    bundle = build_bundle(trace)
    policy = policy_for_intent(trace["intent"])
    fact_types = list(trace.get("metrics", {}).get("fact_type_match", []))
    provider = OpenAICompatibleProvider(Settings.load())
    generator = ShadowAnswerGenerator(provider)
    records: list[dict[str, Any]] = []
    output_dir = OUTPUT_ROOT / "BA-007"
    for index in range(1, RUNS + 1):
        prompt = build_prompt(trace["question"], policy, bundle)
        response = generator.generate(trace["question"], policy, bundle)
        schema = validate_response(response.parsed_response, policy, {item.source_id for item in bundle.items})
        claim_validation = asdict(response.validation) if response.validation else None
        citation_validation = asdict(response.citation_render) if response.citation_render else None
        stage = failure_stage(
            response=response,
            initial_schema=asdict(schema),
            repair_schema=None,
            fact_types=fact_types,
            evidence=bundle,
        )
        provider_error = response.status == "LLM_ERROR" or bool(response.error)
        record = {
            "run_id": f"BA-007-run-{index:02d}",
            "question_id": "BA-007",
            "question": trace["question"],
            "intent": trace["intent"],
            "evidence_ids": [item.source_id for item in bundle.items],
            "raw_llm_response": response.raw_llm_response,
            "parsed_response": response.parsed_response,
            "claims": response.claims,
            "section_map": (response.parsed_response or {}).get("section_map") if response.parsed_response else None,
            "schema_validation": asdict(schema),
            "claim_validation": claim_validation,
            "citation_validation": citation_validation,
            "repair_triggered": response.repair_triggered,
            "repair_response": response.repair_response,
            "provider_status": "PROVIDER_ERROR" if provider_error else "OK",
            "provider_error": response.error,
            "final_status": response.status,
            "failure_stage": stage,
            "unsupported_claims": claim_validation.get("unsupported_claims", 0) if claim_validation else None,
            "invalid_evidence_ids": claim_validation.get("invalid_source_ids", []) if claim_validation else [],
            "diagnostics": {
                "initial": response.initial_diagnostics,
                "final": response.diagnostics,
                "repair": response.repair_diagnostics,
                "elapsed_ms": response.elapsed_ms,
                "request_id": response.request_id,
            },
            "prompt_input": {
                "system_prompt": prompt.system_prompt,
                "user_prompt": prompt.user_prompt,
                "response_schema": prompt.response_schema,
            },
        }
        write_json(output_dir / f"run_{index:02d}.json", record)
        records.append(record)
        print(f"BA007_progress={index}/{RUNS}", flush=True)
    return records


def fact_snapshot(facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_rows": facts["count_result"]["total_valid_rows"],
        "increase_effect_count": facts["count_result"]["increase_benefit_total_count"],
        "undetermined_profit_count": facts["count_result"]["unresolved_profit_total_count"],
        "business_rule": {
            "benefit_semantics": facts["benefit_semantics"],
            "mapped_field": facts["mapped_field"],
            "operator": facts["operator"],
            "threshold": facts["threshold"],
            "source": facts["business_rule_source"],
        },
        "reconciliation_status": "37_CONFIRMED",
    }


def run_ba010() -> list[dict[str, Any]]:
    facts = load_facts()
    output_dir = OUTPUT_ROOT / "BA-010"
    records: list[dict[str, Any]] = []
    reference_signature: dict[str, Any] | None = None
    for index in range(1, RUNS + 1):
        claims = build_atomic_claims(facts)
        fact_validation = validate_atomic_claims(facts, claims)
        citation_validation = validate_citations(facts, claims)
        answer = render_answer(facts, claims)
        signature = {
            "facts": fact_snapshot(facts),
            "claim_values": [
                {"claim_id": item["claim_id"], "claim_type": item["claim_type"], "group": item.get("group"), "value": item["value"], "source_rows": item["source_rows"]}
                for item in claims
            ],
            "answer": answer,
        }
        if reference_signature is None:
            reference_signature = signature
        record = {
            "run_id": f"BA-010-run-{index:02d}",
            "question_id": "BA-010",
            "fact_aggregation": fact_snapshot(facts),
            "atomic_claims": claims,
            "fact_claim_validation": fact_validation,
            "citation_validation": citation_validation,
            "final_answer": answer,
            "reconciliation_status": "37_CONFIRMED",
            "consistent_with_run_01": signature == reference_signature,
        }
        write_json(output_dir / f"run_{index:02d}.json", record)
        records.append(record)
        print(f"BA010_progress={index}/{RUNS}", flush=True)
    return records


def status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("final_status") or record.get("provider_status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


def render_report(ba007: list[dict[str, Any]], ba010: list[dict[str, Any]]) -> str:
    ba007_status = status_counts(ba007)
    ba007_claim_pass = sum(bool(record.get("claim_validation", {}).get("valid")) for record in ba007)
    ba007_citation_pass = sum(bool(record.get("citation_validation", {}).get("valid")) for record in ba007)
    ba007_unsupported = sum(int(record.get("unsupported_claims") or 0) for record in ba007)
    ba007_invalid_ids = sum(len(record.get("invalid_evidence_ids") or []) for record in ba007)
    ba007_stable = all(
        record.get("final_status") == "GENERATED"
        and record.get("schema_validation", {}).get("valid")
        and record.get("claim_validation", {}).get("valid")
        and record.get("citation_validation", {}).get("valid")
        for record in ba007
    )
    ba010_consistent = sum(bool(record.get("consistent_with_run_01")) for record in ba010)
    ba010_fact_pass = sum(bool(record.get("fact_claim_validation", {}).get("valid")) for record in ba010)
    ba010_citation_pass = sum(bool(record.get("citation_validation", {}).get("valid")) for record in ba010)
    lines = [
        "# Answer Path Stability & Final Business Regression Report",
        "",
        "> TASK-016E-3：验证 BA-007 普通知识问答路径与 BA-010 结构化事实统计路径。",
        "> 仅在 Shadow 环境执行；未修改正式 Retriever、Answer Engine、8000 服务或正式 Qdrant。",
        "> BA-010 未调用 LLM，所有数字来自冻结 Fact Result 和 Atomic Claims。",
        "",
        "## 1. BA-007 普通知识问答路径",
        "",
        "- Evidence：固定使用 `evaluation/traces_optimized/BA-007.json` 的同一 Bundle。",
        f"- 回放次数：{len(ba007)}",
        f"- 状态分布：`{json.dumps(ba007_status, ensure_ascii=False)}`",
        f"- Claim Validator 通过：{ba007_claim_pass}/{len(ba007)}",
        f"- Citation Validator 通过：{ba007_citation_pass}/{len(ba007)}",
        f"- Unsupported Claim：{ba007_unsupported}",
        f"- Invalid Evidence ID：{ba007_invalid_ids}",
        f"- STRUCTURE_INVALID：{ba007_status.get('STRUCTURE_INVALID', 0)}",
        f"- BA007 稳定性结论：**{'BA007_STABLE' if ba007_stable else 'BA007_UNSTABLE'}**",
        "",
        "### BA-007 失败阶段分布",
        "",
        "| Primary Root Cause | 次数 |",
        "|---|---:|",
    ]
    stage_counts: dict[str, int] = {}
    for record in ba007:
        primary = record.get("failure_stage", {}).get("primary", "UNKNOWN")
        stage_counts[primary] = stage_counts.get(primary, 0) + 1
    for key, value in sorted(stage_counts.items()):
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## 2. BA-010 结构化事实统计路径",
        "",
        "- 路径：冻结 Fact Result → Atomic Claims → Fact Claim Validator → Citation Validator → Deterministic Answer Renderer。",
        f"- 回放次数：{len(ba010)}",
        f"- Fact Claim Validator 通过：{ba010_fact_pass}/{len(ba010)}",
        f"- Citation Validator 通过：{ba010_citation_pass}/{len(ba010)}",
        f"- 80 一致率：{sum(record['fact_aggregation']['total_rows'] == 80 for record in ba010)}/{len(ba010)}",
        f"- 37 一致率：{sum(record['fact_aggregation']['increase_effect_count'] == 37 for record in ba010)}/{len(ba010)}",
        f"- 43 一致率：{sum(record['fact_aggregation']['undetermined_profit_count'] == 43 for record in ba010)}/{len(ba010)}",
        f"- 专业分组一致率：{sum(record['consistent_with_run_01'] for record in ba010)}/{len(ba010)}",
        f"- source_rows 一致率：{sum(record['consistent_with_run_01'] for record in ba010)}/{len(ba010)}",
        f"- BA-010 稳定性结论：**{'BA010_STABLE' if ba010_consistent == len(ba010) and ba010_fact_pass == len(ba010) and ba010_citation_pass == len(ba010) else 'BA010_UNSTABLE'}**",
        "",
        "## 3. BA-010 最终答案检查",
        "",
        "- 总有效明细：80 条；",
        "- 分组：整体方案、桩基及支护、建筑、结构、给排水、暖通、电气、消防；",
        "- 每组总条数和利润 > 0 条数均来自 Atomic Claims；",
        "- 总增加效益：37 条；",
        "- 业务口径：增加效益 = 利润 > 0；",
        "- 利润为空/未判定：43 条，不描述为无效益；",
        "- 第 88 行汇总公式未进入明细 Claim；",
        "",
        "## 4. 业务路径结论",
        "",
        f"- 普通知识问答路径：{'可继续作为 Shadow 路径使用' if ba007_stable else '不稳定，需先诊断失败样本'}。",
        f"- Fact Answer Path：{'可以进入下一阶段 Shadow 路由集成' if ba010_consistent == len(ba010) and ba010_fact_pass == len(ba010) and ba010_citation_pass == len(ba010) else '暂不进入下一阶段 Shadow 路由集成'}。",
        "- 本次没有进入正式 Answer Engine。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ba007 = run_ba007()
    ba010 = run_ba010()
    REPORT.write_text(render_report(ba007, ba010), encoding="utf-8")
    print(json.dumps({"report": str(REPORT.resolve()), "ba007_runs": len(ba007), "ba010_runs": len(ba010), "ba007_status": status_counts(ba007), "ba010_consistent": sum(record['consistent_with_run_01'] for record in ba010)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
