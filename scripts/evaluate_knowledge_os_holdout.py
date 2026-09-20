from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation" / "knowledge_os_optimization" / "holdout_acceptance.json"
CASES = [
    {"id": "H01", "question": "项目设计创效经济效益额如何计算？", "terms": ["实施后实际取得的经济效益额", "不包括工期效益", "实施前"]},
    {"id": "H02", "question": "设计管理策划包括哪些核心清单？", "terms": ["设计合约规划", "方案比选", "设计风险识别", "设计价值创造"]},
    {"id": "H03", "question": "设计评估报告通常应包括哪些方面？", "terms": ["设计完整性", "设计深度", "技术可行性"]},
    {"id": "H04", "question": "薄壁不锈钢管双卡压和环压应如何比选？", "terms": ["双卡压", "环压"]},
]


def main() -> int:
    rows = []
    with httpx.Client(timeout=180, trust_env=False) as client:
        for case in CASES:
            response = client.post("http://127.0.0.1:8010/api/v2/query", json={"question": case["question"], "trial_user": "reviewer-001", "conversation_id": f"holdout-{case['id']}"})
            response.raise_for_status()
            result = response.json()
            compact = re.sub(r"\s+", "", str(result.get("answer") or ""))
            missing = [term for term in case["terms"] if re.sub(r"\s+", "", term) not in compact]
            rows.append({
                **case,
                "status": result.get("answer_status"),
                "answer_mode": result.get("answer_mode"),
                "generation_mode": result.get("generation_mode"),
                "passed": result.get("answer_status") == "ANSWERED" and not missing and bool(result.get("citations")),
                "missing_terms": missing,
                "answer": result.get("answer"),
                "citations": [{key: item.get(key) for key in ("file_name", "display_location", "source_id", "source_version")} for item in result.get("citations", [])],
            })
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "留出题；本轮未按这些题逐题修改；普通全库入口；预期词来自既有已保存验证结果，仅用于评估",
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("cases", "passed", "failed")}, ensure_ascii=False))
    return 0 if payload["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
