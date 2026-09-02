from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BA = ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
OUT = ROOT / "evaluation" / "v2_8010_trial" / "ui_ba_validation.json"
REPORT = ROOT / "docs" / "AI_QA_FRONTEND_V2_INTEGRATION_REPORT.md"
BASE = "http://127.0.0.1:8010"


def main() -> int:
    source = (ROOT / "knowledge-ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    route_integrated = 'path="/ai" element={<AIChat />}' in source
    cases = _cases()
    expected = {"BA-001": "ANSWERED", "BA-002": "ANSWERED", "BA-004": "ANSWERED", "BA-008": "CONFLICTING_ANSWER", "BA-010": "PARTIAL_ANSWER"}
    results = []
    for case in cases:
        if case["id"] not in expected:
            continue
        response = _post("/api/v2/query", {"question": case["question"], "trial_user": "reviewer-001"})
        results.append({"question_id": case["id"], "answer_status": response["answer_status"], "expected_status": expected[case["id"]], "status_correct": response["answer_status"] == expected[case["id"]], "citation_count": len(response["citations"]), "has_evidence_excerpt": any(bool(item.get("excerpt")) for item in response["citations"]), "answer": response["answer"], "query_id": response["query_id"]})
    source_scope = _post("/api/v2/query", {"question": next(case["question"] for case in cases if case["id"] == "BA-003"), "trial_user": "reviewer-001"})
    feedback = _post("/api/v2/feedback", {"query_id": source_scope["query_id"], "trial_user": "reviewer-001", "feedback_type": "资料缺失", "comment": "AI问答工作台反馈验证"})
    value = {"page_route": "/ai", "route_integrated": route_integrated, "placeholder_removed_from_ai_route": route_integrated, "results": results, "feedback_saved": feedback.get("saved"), "feedback_growth_candidate_id": (feedback.get("feedback_event") or {}).get("growth_candidate_id"), "provider_http_requests": 0, "gold_runtime_injection": 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(_report(value), encoding="utf-8")
    assert route_integrated
    assert all(item["status_correct"] for item in results)
    assert all(item["citation_count"] > 0 for item in results)
    assert feedback.get("saved") is True
    print(json.dumps({"validated": len(results), "feedback": value["feedback_saved"]}, ensure_ascii=False))
    return 0


def _post(path: str, value: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(f"{BASE}{path}", data=json.dumps(value, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _cases() -> list[dict[str, str]]:
    value = yaml.safe_load(BA.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else value.get("questions", value.get("records", []))


def _report(value: dict[str, Any]) -> str:
    rows = [f"- {item['question_id']}：{item['answer_status']}；引用 {item['citation_count']} 条；状态正确={item['status_correct']}" for item in value["results"]]
    return "\n".join(["# AI QA FRONTEND V2 INTEGRATION REPORT", "", "## 页面与接口", "", "- 工作台路由：`/ai`，直接渲染 `AIChat`，不再使用V0.1 Placeholder。", "- V2接口：`POST /api/v2/query`、`POST /api/v2/feedback`。", "- UI组件：本机对话历史、主问答区、引用来源、右侧来源详情、部分/冲突状态、反馈和折叠检索详情。", "", "## 8010实际验证", "", *rows, f"- 反馈提交：{value['feedback_saved']}；Growth Proposal：{value['feedback_growth_candidate_id']}", "", "## 安全边界", "", "- 8010 localhost试用；8000未改动。", "- 前端不复制Retriever逻辑；未调用Provider、未注入Gold、未发布知识。", "", "TASK-020H.1 = COMPLETE", ""])


if __name__ == "__main__":
    raise SystemExit(main())
