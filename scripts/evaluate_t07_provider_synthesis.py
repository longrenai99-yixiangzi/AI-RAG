from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
import winreg
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.answer_engine.llm.provider_runtime_guard import ProviderCircuitBreaker, ProviderRequestBudget, ShadowProviderRuntimeGuard
from app.config import Settings


GUARD_ROOT = ROOT / "evaluation" / "provider_runtime_guard" / "t07_knowledge_os"
OUTPUT = ROOT / "evaluation" / "knowledge_os_optimization" / "t07_provider_synthesis.json"
PUBLIC = ROOT / "evaluation" / "knowledge_os_optimization" / "public_acceptance.json"
SOURCE = Path(r"[LOCAL_PATH_REDACTED]�公司技术部\2025\制度文件\设计中心运行方案\上会\中建三局第二建设公司设计与技术支持中心组织优化及运行方案.pdf")
CASES = [
    {"id": "T07-S01", "question": "中建三局二公司设计与技术支持中心的组织架构是什么样的？", "required": ["公司总部", "各分公司（事业部）", "设计支持岗", "深化设计岗", "方案支持岗", "选择设置"]},
    {"id": "T07-S02", "question": "所有中心都必须设置五个岗位，对吗？", "required": ["均设置", "选择设置"], "required_any": [["不准确", "不对"]]},
    {"id": "T07-S03", "question": "中建三局第二建设公司设计与技术支持中心组织优化及运行方案目前还有效吗？", "required": [], "required_any": [["待核实", "无法判断", "不能判断", "无法确认", "不能确认"], ["没有证明", "未包含方案的有效期", "未包含有效期", "未包含废止", "未包含修订"]]},
]


def main() -> int:
    settings = _official_settings()
    budget = ProviderRequestBudget(GUARD_ROOT / "provider_budget.json", task_id="TASK-KNOWLEDGE-OS-T07-1", provider="deepseek_official_openai_compatible", model=settings.chat_model, max_real_requests=10)
    circuit = ProviderCircuitBreaker(GUARD_ROOT / "provider_circuit.json", threshold=2, cooldown_seconds=60)

    def telemetry(row):
        with (GUARD_ROOT / "runtime_guard_telemetry.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    guard = ShadowProviderRuntimeGuard(settings, budget, circuit, max_attempts=1, telemetry_sink=telemetry)
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    public_by_question = {row["question"]: row for row in public["rows"]}
    with pymupdf.open(SOURCE) as document:
        source_text = document[0].get_text()
    rows = []
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        for row in previous.get("rows", []):
            validation = row.get("validation") or {}
            answer = str(row.get("generated_answer") or "")
            has_citation = bool(re.findall(r"(?<![A-Za-z0-9])(S\d+)(?![A-Za-z0-9])", answer))
            case = next((item for item in CASES if item["id"] == row.get("id")), None)
            missing = _missing_terms(answer, case) if case else ["UNKNOWN_CASE"]
            if row.get("provider", {}).get("final_status") == "GENERATION_READY" and has_citation and not missing and not any(validation.get(key) for key in ("invalid_citations", "unsupported_numbers")):
                rows.append({**row, "passed": True, "validation": {**validation, "missing_required_terms": []}})
    for case in CASES:
            if any(row.get("id") == case["id"] and row.get("passed") for row in rows):
                continue
            baseline = public_by_question[case["question"]]
            citation = baseline["citations"][0]
            allowed = ["S1"]
            evidence = [{"citation": "S1", "source_id": citation.get("source_id"), "source_version": citation.get("source_version"), "location": citation.get("display_location"), "text": source_text}]
            result = guard.generate(
                "你是企业知识库的受约束归纳器。只能使用给定证据；保留组织、数字、日期、否定、必须/选择设置、条件和例外；每项事实标注给定引用；不得补充外部知识。只返回JSON对象，格式为{\"answer\":\"...\"}。",
                json.dumps({"question": case["question"], "evidence": evidence}, ensure_ascii=False),
                temperature=0,
                max_tokens=700,
                telemetry_context={"request_id": "t07-" + uuid.uuid4().hex, "pipeline_run_id": "TASK-KNOWLEDGE-OS-T07-1", "question_id": case["id"]},
            )
            if result.final_status != "GENERATION_READY":
                rows.append({"id": case["id"], "passed": False, "provider": {key: value for key, value in result.to_dict().items() if key != "content"}, "reason": "PROVIDER_NOT_READY"})
                break
            answer = _answer_text(result.content)
            missing = _missing_terms(answer, case)
            citations = re.findall(r"(?<![A-Za-z0-9])(S\d+)(?![A-Za-z0-9])", answer)
            invalid_citations = [value for value in citations if value not in allowed]
            evidence_numbers = set(re.findall(r"\d+(?:\.\d+)?", case["question"] + " ".join(item["text"] for item in evidence)))
            unsupported_numbers = sorted(set(re.findall(r"\d+(?:\.\d+)?", answer)) - evidence_numbers)
            passed = not missing and bool(citations) and not invalid_citations and not unsupported_numbers
            rows.append({
                "id": case["id"], "question": case["question"], "passed": passed,
                "baseline": {"answer": baseline.get("answer"), "answer_status": baseline.get("status"), "citations": allowed},
                "generated_answer": answer,
                "validation": {"missing_required_terms": missing, "invalid_citations": invalid_citations, "unsupported_numbers": unsupported_numbers},
                "provider": {key: value for key, value in result.to_dict().items() if key != "content"},
            })
            if not passed:
                break
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "api_host": "api.deepseek.com", "model": settings.chat_model,
        "api_key_fingerprint": hashlib.sha256(settings.api_key.encode()).hexdigest()[:12],
        "cases_planned": len(CASES), "cases_run": len(rows), "passed": sum(row["passed"] for row in rows), "failed": sum(not row["passed"] for row in rows),
        "comparison": {
            "improved": sum(_comparison(row) == "IMPROVED" for row in rows),
            "equivalent": sum(_comparison(row) == "EQUIVALENT" for row in rows),
            "worse": sum(_comparison(row) == "WORSE" for row in rows),
        },
        "budget": budget.snapshot(), "circuit": circuit.snapshot(), "rows": [{**row, "comparison_to_deterministic": _comparison(row)} for row in rows],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("cases_planned", "cases_run", "passed", "failed", "budget", "circuit")}, ensure_ascii=False))
    return 0 if len(rows) == len(CASES) and payload["failed"] == 0 else 1


def _official_settings() -> Settings:
    values = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in ("RAG_API_KEY", "RAG_API_BASE_URL", "RAG_CHAT_MODEL"):
            values[name] = str(winreg.QueryValueEx(key, name)[0]).strip()
    return replace(Settings.load(), api_key=values["RAG_API_KEY"], api_base_url=values["RAG_API_BASE_URL"].rstrip("/"), chat_model=values["RAG_CHAT_MODEL"])


def _answer_text(content: str) -> str:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    parsed = json.loads(value)
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        raise ValueError("PROVIDER_ANSWER_EMPTY")
    return answer


def _missing_terms(answer: str, case: dict) -> list[str]:
    compact = re.sub(r"\s+", "", answer)
    missing = [term for term in case["required"] if re.sub(r"\s+", "", term) not in compact]
    missing.extend("/".join(group) for group in case.get("required_any", []) if not any(re.sub(r"\s+", "", term) in compact for term in group))
    return missing


def _comparison(row: dict) -> str:
    if not row.get("passed"):
        return "WORSE"
    answer = str(row.get("generated_answer") or "")
    if row.get("id") == "T07-S02" and all(term in answer for term in ("并非所有中心", "选择设置")):
        return "IMPROVED"
    if row.get("id") == "T07-S03" and sum(term in answer for term in ("有效期", "废止", "修订")) >= 2:
        return "IMPROVED"
    return "EQUIVALENT"


if __name__ == "__main__":
    raise SystemExit(main())
