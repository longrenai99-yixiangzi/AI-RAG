from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_claim_preflight_safety_gate import (
    generic_cases,
    render_report,
    run_generic_tests,
)
from scripts.run_p0_integrated_shadow_regression import ShadowIntegratedAnswerPipeline, read_json, write_json
from scripts.shadow_answer_router_v1 import load_ba_questions


OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "claim_preflight_positive_path"
REPORT = PROJECT_ROOT / "docs" / "CLAIM_PREFLIGHT_POSITIVE_PATH_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="TASK-017E-1.1 positive-path verification")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        ba_rows = [read_json(path) for path in sorted(OUTPUT_DIR.glob("BA-*.json"))]
        generic = [read_json(path) for path in sorted((OUTPUT_DIR / "generic").glob("*.json"))]
        REPORT.write_text(render_report(ba_rows, generic, artifact_dir="evaluation/claim_preflight_positive_path"), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "mode": "report-only"}, ensure_ascii=False, indent=2))
        return 0

    pipeline = ShadowIntegratedAnswerPipeline()
    try:
        questions = {question_id: question for question_id, question, _ in load_ba_questions()}
        ba_rows: list[dict[str, object]] = []
        for index in range(1, 11):
            question_id = f"BA-{index:03d}"
            row = pipeline.run(question_id, questions[question_id])
            row["fresh_run"] = True
            write_json(OUTPUT_DIR / f"{question_id}.json", row)
            ba_rows.append(row)
            print(f"positive_ba={question_id}", flush=True)
        generic = run_generic_tests({str(row["question_id"]): row for row in ba_rows})
        for item in generic:
            write_json(OUTPUT_DIR / "generic" / f"{item['test_id']}.json", item)
        REPORT.write_text(render_report(ba_rows, generic, artifact_dir="evaluation/claim_preflight_positive_path"), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "ba_runs": len(ba_rows), "generic_tests": len(generic), "generic_pass": sum(item['result'] == 'PASS' for item in generic)}, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
