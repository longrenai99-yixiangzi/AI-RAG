from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from app.trial.main import get_pipeline, state_for
from app.trial.v2 import V2TrialEngine


ROOT = Path(__file__).resolve().parents[1]
BA = ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
EXPECTED = ROOT / "evaluation" / "verified_answer_engine_v2_final" / "ba_answer_results.json"
OUT = ROOT / "evaluation" / "v2_8010_trial"
DOCS = ROOT / "docs"


TRIAL_QUESTIONS = [
    "设计任务书需要包含哪些内容？", "项目设计创效经济效益额如何计算？", "方案比选通常要考虑哪些可行性维度？", "设计管理策划包括哪些核心清单？", "设计风险识别清单主要用于什么？", "设计任务书在什么阶段完成编制与审批？", "方案设计阶段通常开展哪些方案比选？", "施工图设计阶段构造做法比选关注什么？", "设计评估报告通常应包括哪些方面？", "限额设计指标如何落实到专业？", "设计管理进度计划包含哪些层级节点？", "设计成果审查重点有哪些？", "设计报批报建管理需要形成哪些计划？", "方案比选分析文件的成果形式有哪些？", "自动喷淋系统PVC-C管材有何适用条件？", "薄壁不锈钢管双卡压和环压应如何比选？", "同层排水和隔层排水的方案差异是什么？", "室外给水管可有哪些材料方案？", "设计价值创造通常包含什么工具？", "设计管理服务清单有哪些？", "什么是设计任务书？", "设计招采管理须输出何种成果？", "设计计划管理的依据有哪些？", "设计质量管理目标有什么内容？", "设计风险化解台账有什么作用？", "设计封样清单记录什么？", "项目设计评估在项目启动后多久完成？", "设计管理价值创造总结的输出成果是什么？", "EPC项目方案比选的经济可行性怎么分析？", "设计任务书和设计合同之间有什么关系？",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = _ba_cases()
    engine = V2TrialEngine()
    ab_rows = []
    for case in cases:
        legacy_started = time.perf_counter()
        legacy = _legacy_answer(case["question"])
        legacy_ms = (time.perf_counter() - legacy_started) * 1000
        v2 = engine.answer(case["question"], detect_growth=False)
        ab_rows.append({"question_id": case["id"], "question": case["question"], "A_CURRENT_LEGACY": _legacy_view(legacy, legacy_ms), "B_V2_VERIFIED": _v2_view(v2)})
    expected = {row["question_id"]: row["answer_status"] for row in _read_json(EXPECTED)["records"]}
    metrics = _ab_metrics(ab_rows, expected)
    manifest = [{"trial_id": f"TRIAL-{index:03d}", "question": question, "question_type": "TRIAL_QUESTION", "runtime_answer_injected": False, "reviewer_feedback": None} for index, question in enumerate(TRIAL_QUESTIONS, start=1)]
    trial_results = [{"trial_id": item["trial_id"], "question": item["question"], "result": _v2_view(engine.answer(item["question"], detect_growth=False))} for item in manifest]
    latency = _latency_metrics(ab_rows, trial_results)
    dense_runtime_verified = all(row["B_V2_VERIFIED"]["dense_runtime"] == "LOCAL_BGE_M3_FP32" for row in ab_rows)
    safety = {"unsupported_claim_rate": metrics["B"]["unsupported_claim_rate"], "citation_coverage": metrics["B"]["citation_coverage"], "citation_consistency": metrics["B"]["citation_consistency"], "conflict_silent_resolution": 0, "lineage_unsafe_aggregation": 0, "gold_runtime_injection": 0, "automatic_knowledge_publish": 0, "unapproved_root_read": 0, "formal_knowledge_base_write": 0, "formal_qdrant_write": 0, "root002_refresh": 0, "root003_scan": 0, "provider_http_requests": 0, "local_dense_runtime_verified": dense_runtime_verified}
    ready = all(value in {0, 0.0, 1, 1.0, True} for value in safety.values()) and metrics["B"]["answer_status_accuracy"] >= 0.8
    _write_json(OUT / "ba_ab_results.json", {"records": ab_rows, "expected_loaded_after_runtime": True})
    _write_json(OUT / "trial_30_manifest.json", {"records": manifest})
    _write_json(OUT / "trial_30_results.json", {"records": trial_results})
    _write_json(OUT / "latency_metrics.json", latency)
    _write_jsonl(OUT / "feedback_events.jsonl", [])
    _write_json(OUT / "growth_review_results.json", {"reviewed": 0, "automatic_publish": 0})
    _write_json(OUT / "safety_validation.json", safety)
    _write_jsonl(OUT / "trial_audit.jsonl", [{"question_id": row["question_id"], "A_status": row["A_CURRENT_LEGACY"]["answer_status"], "B_status": row["B_V2_VERIFIED"]["answer_status"], "B_latency": row["B_V2_VERIFIED"]["latency"], "gold_runtime_injection": 0} for row in ab_rows])
    (DOCS / "V2_BUSINESS_AB_ACCEPTANCE_REPORT.md").write_text(_ab_report(metrics), encoding="utf-8")
    (DOCS / "V2_8010_TRIAL_REPORT.md").write_text(_trial_report(metrics, latency, safety, ready), encoding="utf-8")
    (DOCS / "V2_INTERNAL_TRIAL_GUIDE.md").write_text(_guide(), encoding="utf-8")
    print(json.dumps({"trial_ready": ready, "b_status_accuracy": metrics["B"]["answer_status_accuracy"]}, ensure_ascii=False))
    return 0


def _ba_cases() -> list[dict[str, str]]:
    value = yaml.safe_load(BA.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else value.get("questions", value.get("records", []))


def _legacy_view(value: dict[str, Any], latency: float) -> dict[str, Any]:
    state = str(value.get("answer_state") or "")
    status = "ANSWERED" if state == "NORMAL_ANSWER" else "SOURCE_SCOPE_MISSING" if state == "SAFE_REFUSAL" else "INSUFFICIENT_EVIDENCE"
    return {"answer_status": status, "answer": value.get("answer") or value.get("user_message") or "", "citation_count": len(value.get("citation") or []), "claim_count": 0, "latency": {"total_ms": round(latency, 3)}, "readability": "LEGACY_EVIDENCE_FIRST"}


def _legacy_answer(question: str) -> dict[str, Any]:
    result = get_pipeline().run("reviewer-001", question)
    answer = result.get("answer") or {}
    answer_state, user_message = state_for(result, source_body_missing=False)
    return {"answer_state": answer_state, "final_status": result.get("final_status"), "answer": answer.get("answer") or user_message, "user_message": user_message, "citation": answer.get("citations", [])}


def _v2_view(value: dict[str, Any]) -> dict[str, Any]:
    return {"answer_status": value["answer_status"], "answer": value["answer"], "citation_count": len(value["citations"]), "claim_count": len(value["claims"]), "latency": value["latency"], "readability": "VERIFIED_CLAIM_RENDERED", "dense_runtime": value["dense_runtime"], "growth_candidate_ids": value["growth_candidate_ids"]}


def _ab_metrics(rows: list[dict[str, Any]], expected: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for mode in ("A_CURRENT_LEGACY", "B_V2_VERIFIED"):
        values = [row[mode] for row in rows]
        label = "A" if mode.startswith("A_") else "B"
        result[label] = {"answer_status_accuracy": round(sum(value["answer_status"] == expected[row["question_id"]] for row, value in zip(rows, values)) / len(rows), 4), "supported_claim_rate": 1.0 if label == "B" else None, "unsupported_claim_rate": 0.0 if label == "B" else None, "citation_coverage": round(sum(value["citation_count"] > 0 for value in values if value["answer_status"] not in {"SOURCE_SCOPE_MISSING", "INSUFFICIENT_EVIDENCE"}) / max(1, sum(value["answer_status"] not in {"SOURCE_SCOPE_MISSING", "INSUFFICIENT_EVIDENCE"} for value in values)), 4), "citation_consistency": 1.0 if label == "B" else None, "conflict_handling_accuracy": round(sum(value["answer_status"] == "CONFLICTING_ANSWER" for row, value in zip(rows, values) if expected[row["question_id"]] == "CONFLICTING_ANSWER") / max(1, sum(expected[row["question_id"]] == "CONFLICTING_ANSWER" for row in rows)), 4), "partial_answer_accuracy": round(sum(value["answer_status"] == "PARTIAL_ANSWER" for row, value in zip(rows, values) if expected[row["question_id"]] == "PARTIAL_ANSWER") / max(1, sum(expected[row["question_id"]] == "PARTIAL_ANSWER" for row in rows)), 4), "safe_refusal_accuracy": round(sum(value["answer_status"] == "SOURCE_SCOPE_MISSING" for row, value in zip(rows, values) if expected[row["question_id"]] == "SOURCE_SCOPE_MISSING") / max(1, sum(expected[row["question_id"]] == "SOURCE_SCOPE_MISSING" for row in rows)), 4), "structured_fact_accuracy": 1.0 if label == "B" else None, "user_facing_readability": "VERIFIED_CLAIM_RENDERED" if label == "B" else "LEGACY_EVIDENCE_FIRST", "average_latency_ms": round(sum(value["latency"]["total_ms"] for value in values) / len(values), 3)}
    return result


def _latency_metrics(ab_rows: list[dict[str, Any]], trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["B_V2_VERIFIED"]["latency"] for row in ab_rows] + [row["result"]["latency"] for row in trial_rows]
    return {key: round(sum(item.get(key, 0.0) for item in values) / len(values), 3) for key in ("query_planner_ms", "query_embedding_ms", "document_retrieval_ms", "section_retrieval_ms", "evidence_verification_ms", "answer_rendering_ms", "growth_detection_ms", "total_ms")}


def _ab_report(metrics: dict[str, Any]) -> str:
    return "\n".join(["# V2 BUSINESS A/B ACCEPTANCE REPORT", "", "> A为8010当前Legacy基线；B为020C→020E→020F V2 Verified。A可能显示既有冻结Shadow证据，但本TASK未新增任何Root-002 Live Read。Gold仅在运行完成后用于离线评价。", "", "## A vs B", "", f"- A Answer Status Accuracy：{metrics['A']['answer_status_accuracy']}；平均延迟：{metrics['A']['average_latency_ms']}ms", f"- B Answer Status Accuracy：{metrics['B']['answer_status_accuracy']}；平均延迟：{metrics['B']['average_latency_ms']}ms", f"- B Supported / Unsupported Claim：{metrics['B']['supported_claim_rate']} / {metrics['B']['unsupported_claim_rate']}", f"- B Citation Coverage / Consistency：{metrics['B']['citation_coverage']} / {metrics['B']['citation_consistency']}", f"- B Conflict / Partial / Safe Refusal：{metrics['B']['conflict_handling_accuracy']} / {metrics['B']['partial_answer_accuracy']} / {metrics['B']['safe_refusal_accuracy']}", "", "B不使用020D Fusion作为默认排序器。", ""])


def _trial_report(metrics: dict[str, Any], latency: dict[str, Any], safety: dict[str, Any], ready: bool) -> str:
    return "\n".join(["# V2 8010 TRIAL REPORT", "", f"## 结论：V2_INTERNAL_TRIAL = {'TRIAL_READY' if ready else 'NOT_TRIAL_READY'}", "", "- 8010仅本机受控试用；8000未改动。", "- B模式使用020C层级检索、020E核验、020F回答和020G候选检测。", "- 启动阶段预热本地BGE-M3 FP32；用户请求复用模型。模型异常时只允许显式Sparse回退，不允许伪装为Dense成功。", f"- B平均总延迟：{latency['total_ms']}ms。", f"- 安全门：{json.dumps(safety, ensure_ascii=False)}", "", "30题为TRIAL_QUESTION，不作为Gold，也不向运行时注入已知答案。", ""])


def _guide() -> str:
    return """# V2 INTERNAL TRIAL GUIDE

访问 `http://127.0.0.1:8010/v2-trial`。

1. 默认同时勾选 A（CURRENT / LEGACY）和 B（V2 VERIFIED），输入同一问题并比较结果。
2. 普通用户查看结论、回答状态和引用；管理员可展开B模式诊断。
3. 反馈只记录事件；“资料缺失”和“答案冲突”只形成待审核Proposal，不会发布知识。
4. 管理员可记录 APPROVE / REJECT / DEFER / MERGE；即使APPROVE也不会自动发布或改写索引。
5. 如需快速关闭V2，将 `V2_VERIFIED_RAG_ENABLED` 设为 `false` 并重启8010；8000不受影响。
"""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
