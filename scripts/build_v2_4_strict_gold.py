from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
ANSWER_GOLD = V23 / "gold" / "answer_gold.jsonl"
OWNER_GOLD = ROOT / "evaluation" / "business_gold_v2" / "owner_approved_gold_manifest.json"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def variant(text: str) -> str:
    text = text.replace("这一行", "该行").replace("这一行的", "该行的")
    text = text.replace("分别是什么？", "请分别列出。")
    text = text.replace("是什么？", "请直接给出原文内容。")
    return "请根据同一来源回答：" + text


def main() -> int:
    source = [row for row in read(ANSWER_GOLD) if str(row.get("verification_status")) in {"OWNER_CONFIRMED", "CONFIRMED"}]
    owners = {str(row.get("question_id")): row for row in (json.loads(OWNER_GOLD.read_text(encoding="utf-8")).get("records") or [])} if OWNER_GOLD.exists() else {}
    if len(source) != 30:
        raise RuntimeError(f"expected 30 confirmed Answer Gold rows, got {len(source)}")
    strict, variants = [], []
    for index, row in enumerate(source, start=1):
        evidence = row.get("required_evidence")
        evidence = evidence if isinstance(evidence, list) else [evidence] if evidence else []
        owner = owners.get(str(row.get("question_id"))) or {}
        if owner.get("gold_primary_source") and not any(isinstance(item, dict) and item.get("source_path") for item in evidence):
            evidence = [{"source_path": owner["gold_primary_source"], "file_name": Path(owner["gold_primary_source"]).name, **(evidence[0] if evidence and isinstance(evidence[0], dict) else {})}, *evidence]
        sources = [str(item.get("source_path") or item.get("file_name") or "") for item in evidence if isinstance(item, dict) and (item.get("source_path") or item.get("file_name"))]
        sections = [str(item.get("section") or item.get("section_path") or "") for item in evidence if isinstance(item, dict) and (item.get("section") or item.get("section_path"))]
        record = {
            "regression_id": f"SRG-{index:03d}",
            "source_answer_gold_id": row.get("question_id"),
            "question": row.get("question"),
            "expected_claims": [str(claim) for claim in row.get("expected_claims") or [] if str(claim).strip() and not str(claim).strip().endswith("：")],
            "required_evidence": evidence,
            "acceptable_sources": sources,
            "acceptable_sections": sections,
            "acceptable_scope": {"sources": sources, "sections": sections, "table_rows": [{"table_id": item.get("table_id"), "row": item.get("row")} for item in evidence if isinstance(item, dict) and item.get("table_id")]},
            "unacceptable_claims": [],
            "expected_answer_mode": "ANSWERED",
            "citation_required": True,
            "verification_status": "OWNER_CONFIRMED",
            "verified_from_answer_gold": True,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }
        strict.append(record)
        variants.append({"variant_id": f"SRV-{index:03d}-A", "regression_id": record["regression_id"], "question": variant(str(row.get("question") or "")), "expected_claims": record["expected_claims"], "required_evidence": record["required_evidence"], "acceptable_scope": record["acceptable_scope"], "expected_answer_mode": record["expected_answer_mode"], "citation_required": True, "verified_from_answer_gold": True})
    V24.mkdir(parents=True, exist_ok=True)
    (V24 / "strict_regression_gold.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_4.strict_regression_gold", "status": "OWNER_CONFIRMED", "count": len(strict), "source": str(ANSWER_GOLD), "records": strict}, ensure_ascii=False, indent=2), encoding="utf-8")
    (V24 / "strict_regression_variants.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_4.strict_regression_variants", "status": "INHERITED_FROM_ANSWER_GOLD", "count": len(variants), "records": variants}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"strict_gold": len(strict), "variants": len(variants), "source": str(ANSWER_GOLD)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
