#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对若干「只能抛原文摘录」的题目，直接调用 pipeline.run() 打印内部诊断。

用法（项目目录下）：
    .venv\\Scripts\\python.exe scripts\\trial_qa_why_blocked.py Q02 Q07 Q31
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trial import main as trial_main

BENCH = PROJECT_ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl"


def main() -> int:
    wanted = [item.strip().upper() for item in sys.argv[1:] if item.strip()]
    rows = [json.loads(line) for line in BENCH.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["question_id"]: row for row in rows}
    if not wanted:
        wanted = list(by_id)[:3]

    pipeline = trial_main.get_pipeline()
    for qid in wanted:
        row = by_id.get(qid)
        if row is None:
            print(f"[skip] unknown qid {qid}")
            continue
        result = pipeline.run(qid, row["question"])
        answer = result.get("answer") or {}
        route = result.get("route") or {}
        print("=" * 78)
        print(f"{qid}  {row['question']}")
        print(f"  route            : {route.get('route')} / fact_mode={route.get('fact_mode')} / intent={route.get('intent')}")
        print(f"  answer_path      : {result.get('answer_path')}")
        print(f"  final_status     : {result.get('final_status')}")
        print(f"  provider_status  : {answer.get('provider_status')}")
        print(f"  preflight        : {(result.get('claim_preflight') or {}).get('claim_preflight_status')}"
              f"  provider_should_run={(result.get('claim_preflight') or {}).get('provider_should_run')}"
              f"  reasons={(result.get('claim_preflight') or {}).get('preflight_reason_codes')}")
        print(f"  provider_error   : {str(answer.get('provider_error'))[:180]}")
        print(f"  initial_status   : {answer.get('initial_status')}")
        schema = answer.get("schema_validation") or {}
        print(f"  schema_validation: valid={schema.get('valid')} category={schema.get('category')} errors={str(schema.get('errors'))[:200]}")
        section = answer.get("section_map_validation") or {}
        print(f"  section_map      : valid={section.get('valid')} errors={str(section.get('errors'))[:160]}")
        claim = answer.get("claim_validation") or {}
        print(f"  claim_validation : valid={claim.get('valid')} errors={str(claim.get('errors'))[:160]}")
        raw = str(answer.get("raw_llm_response") or "")
        print(f"  raw_llm (first 320): {raw[:320]!r}")
        print(f"  selected evidence:")
        for item in (result.get("selected_evidence") or [])[:5]:
            print(f"     - {str(item.get('file_name'))[:52]} | {str(item.get('source_path'))[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
