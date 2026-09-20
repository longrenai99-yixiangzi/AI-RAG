from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation" / "knowledge_os_optimization" / "public_acceptance.json"
ENDPOINT = "http://127.0.0.1:8010/api/v2/query"

CASES = [
    {"id": "O01", "question": "中建三局二公司设计与技术支持中心的组织架构是什么样的？", "statuses": ["ANSWERED"], "answer_terms": ["公司总部设置", "各分公司（事业部）均设置", "设计支持岗", "深化设计岗", "方案支持岗", "区域分公司中心选择设置", "专业公司中心选择设置"], "source_terms": ["均设置设计支持岗", "选择设置技术投标岗"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O02", "question": "二公司总部中心隶属哪个部门？", "statuses": ["ANSWERED"], "answer_terms": ["公司设计与技术管理部二级部室"], "source_terms": ["作为公司设计与技术管理部二级部室"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O03", "question": "分公司中心共同设置哪些岗位？", "statuses": ["ANSWERED"], "answer_terms": ["设计支持岗", "深化设计岗", "方案支持岗"], "source_terms": ["均设置设计支持岗"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O04", "question": "区域分公司中心可以另设什么岗位？", "statuses": ["ANSWERED"], "answer_terms": ["选择设置", "技术投标岗", "钢筋翻样岗"], "source_terms": ["区域分公司中心选择设置"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O05", "question": "专业公司中心必须设钢筋翻样岗吗？", "statuses": ["ANSWERED"], "answer_terms": ["不能认定", "专业公司中心选择设置技术投标岗"], "source_terms": ["专业公司中心选择设置技术投标岗"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O06", "question": "所有中心都必须设置五个岗位，对吗？", "statuses": ["ANSWERED"], "answer_terms": ["该说法不准确", "均设置设计支持岗", "选择设置"], "source_terms": ["均设置设计支持岗", "选择设置技术投标岗"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "O07", "question": "中建三局第二建设公司设计与技术支持中心与二公司设计与技术支持中心是什么关系？", "statuses": ["ANSWERED"], "answer_terms": ["归一为同一组织称谓", "只用于查询和范围识别", "不据此合并其他公司的中心"], "source_terms": ["中建三局第二建设公司", "二公司"], "source": "组织别名配置（系统）", "location": "系统配置 ORGANIZATION_ALIASES"},
    {"id": "O08", "question": "星谷科创中心项目有哪些信息？", "statuses": ["ANSWERED", "PARTIAL_ANSWER"], "answer_terms": [], "source_terms": [], "source": "星谷", "project_scope": "星谷科创中心项目"},
    {"id": "O09", "question": "中建三局第二建设公司设计与技术支持中心组织优化及运行方案目前还有效吗？", "statuses": ["PARTIAL_ANSWER"], "answer_terms": ["没有证明它是现行有效版本", "待核实"], "source_terms": ["组织优化及运行方案"], "source": "组织优化及运行方案.pdf", "location": "第1页"},
    {"id": "G01", "question": "设计任务书需要包含哪些内容？", "statuses": ["ANSWERED"], "answer_terms": ["项目概况", "工作范围", "工作要求", "设计技术要点"], "source_terms": ["项目概况", "工作范围", "工作要求", "设计技术要点"], "source": "《项目设计管理手册》.pdf", "location": "第17页"},
    {"id": "G02", "question": "平鲁风电项目任务书涉及哪些专业？", "statuses": ["ANSWERED"], "answer_terms": ["总图", "风机", "集电线路", "风场道路"], "source_terms": ["总图", "风机", "集电线路"], "source": "平鲁风电项目", "location": "第185-186段"},
]


def main() -> int:
    rows = []
    with httpx.Client(timeout=180, trust_env=False) as client:
        for case in CASES:
            response = client.post(ENDPOINT, json={"question": case["question"], "trial_user": "reviewer-001", "conversation_id": f"public-acceptance-{case['id']}"})
            response.raise_for_status()
            result = response.json()
            answer = str(result.get("answer") or "")
            citations = result.get("citations") or []
            citation_text = "\n".join(str(item.get("excerpt") or "") for item in citations)
            compact_answer = re.sub(r"\s+", "", answer)
            compact_citation_text = re.sub(r"\s+", "", citation_text)
            source_hit = any(case["source"] in str(item.get("file_name") or "") for item in citations)
            location_hit = not case.get("location") or any(case["location"] == str(item.get("display_location") or "") for item in citations)
            project_scope_hit = not case.get("project_scope") or case["project_scope"] in ((result.get("debug") or {}).get("query_plan") or {}).get("project", [])
            required_missing = [term for term in case["answer_terms"] if re.sub(r"\s+", "", term) not in compact_answer]
            unsupported_source_terms = [term for term in case["source_terms"] if re.sub(r"\s+", "", term) not in compact_citation_text]
            conclusion_correct = result.get("answer_status") in case["statuses"] and project_scope_hit and not required_missing
            citation_supported = source_hit and location_hit and not unsupported_source_terms
            passed = conclusion_correct and citation_supported
            rows.append({"id": case["id"], "question": case["question"], "status": result.get("answer_status"), "answer_mode": result.get("answer_mode"), "source_hit": source_hit, "location_hit": location_hit, "project_scope_hit": project_scope_hit, "conclusion_correct": conclusion_correct, "citation_supported": citation_supported, "missing_answer_terms": required_missing, "missing_source_terms": unsupported_source_terms, "passed": passed, "answer": answer, "citations": [{key: item.get(key) for key in ("source_id", "file_name", "display_location", "source_version")} for item in citations]})
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "PUBLIC_REGRESSION_CASES; ordinary full-corpus endpoint; no expected source injected into runtime",
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "retrieval_source_hit": {"numerator": sum(row["source_hit"] for row in rows), "denominator": len(rows)},
        "final_evidence_hit": {"numerator": sum(row["source_hit"] and row["location_hit"] for row in rows), "denominator": len(rows)},
        "conclusion_correct": {"numerator": sum(row["conclusion_correct"] for row in rows), "denominator": len(rows)},
        "answer_required_fact_coverage": {"numerator": sum(not row["missing_answer_terms"] for row in rows), "denominator": len(rows)},
        "citation_fact_support": {"numerator": sum(row["citation_supported"] for row in rows), "denominator": len(rows)},
        "erroneous_refusals": {"numerator": sum(row["status"] in {"SOURCE_SCOPE_MISSING", "INSUFFICIENT_EVIDENCE"} for row in rows), "denominator": len(rows)},
        "rows": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("cases", "passed", "failed", "retrieval_source_hit", "final_evidence_hit", "conclusion_correct", "answer_required_fact_coverage", "citation_fact_support", "erroneous_refusals")}, ensure_ascii=False))
    return 0 if payload["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
