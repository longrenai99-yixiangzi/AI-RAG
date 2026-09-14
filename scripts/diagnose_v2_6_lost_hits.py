from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence


ROOT = Path(__file__).resolve().parents[1]
V25_STAGE = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
MANUAL_REVIEW = V26 / "live_shadow_manual_review.json"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _find_target_pdf(documents: list[dict[str, Any]]) -> Path:
    # Resolve through an existing source path to avoid console code-page issues.
    year_dirs = set()
    for row in documents:
        path = Path(str(row.get("source_path") or ""))
        for parent in path.parents:
            if parent.name == "2026":
                year_dirs.add(parent)
    matches = []
    for year_dir in year_dirs:
        try:
            matches.extend(path for path in year_dir.rglob("04.*.pdf") if path.is_file() and path.stat().st_size == 4_422_163)
        except OSError:
            continue
    if not matches:
        raise FileNotFoundError("LSR-014 physical PDF not found")
    return sorted(matches, key=lambda path: str(path).casefold())[0]


def _metric_context(path: Path, needle: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    contexts: list[str] = []
    start = 0
    while (index := text.find(needle, start)) >= 0:
        contexts.append(" ".join(text[max(0, index - 180) : index + 180].split()))
        start = index + len(needle)
    return contexts


def _parse_target(target: Path) -> dict[str, Any]:
    builder = DocumentIntelligenceV2Builder(target.parents[3])
    atomic = build_atomic_evidence(target, target.parents[3]).get("records") or []
    parsed = builder.build([target], atomic)
    document = (parsed.get("documents") or [{}])[0]
    hits = []
    for paragraph in parsed.get("paragraphs") or []:
        text = str(paragraph.get("text") or "")
        if any(term in text for term in ("\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a", "2035\u603b\u4f53\u884c\u52a8\u89c4\u5212", "\u4f9d\u62588\u4e2aBIM", "\u5149\u8c37\u5143\u8457")):
            hits.append({"text": text, "location": paragraph.get("location"), "section_id": paragraph.get("section_id")})
    return {
        "physical_exists": target.is_file(),
        "path": str(target),
        "file_size_bytes": target.stat().st_size,
        "sha256": _sha(target),
        "parse_status": document.get("parse_status"),
        "document_id": document.get("document_id"),
        "paragraph_count": len(parsed.get("paragraphs") or []),
        "atomic_evidence_count": len(parsed.get("atomic_evidence") or []),
        "evidence_hits": hits,
    }


def _diagnosis() -> dict[str, Any]:
    manual = json.loads(MANUAL_REVIEW.read_text(encoding="utf-8"))
    reviewed = {row.get("review_id"): row for row in manual.get("records") or []}
    documents = _read_jsonl(V25_STAGE / "documents.jsonl")
    target = _find_target_pdf(documents)
    target_name = target.name
    exact_name = [row for row in documents if row.get("file_name") == target_name]
    registration = [row for row in documents if row.get("document_type") == "REGISTER_PAGE" and "04." in json.dumps(row, ensure_ascii=False)]
    source_paths = {}
    for row in documents:
        name = str(row.get("file_name") or "")
        path = Path(str(row.get("source_path") or ""))
        if name.startswith("2025") and name.endswith(".md") and path.is_file():
            text = path.read_text(encoding="utf-8")
            if "3.31" in text or "3.33" in text:
                source_paths[name] = str(path)
    metric_contexts = {
        name: {needle: _metric_context(Path(path), needle) for needle in ("3.31", "3.33")}
        for name, path in source_paths.items()
    }
    return {
        "schema_version": "knowledge_os_v2_6.lost_hit_remediation_diagnosis",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "release_boundary": {
            "v2_5_frozen_candidate_unchanged": True,
            "formal_8000_touched": False,
            "8010_switch_performed": False,
            "status": "DIAGNOSIS_ONLY_NEW_REMEDIATION_CANDIDATE_REQUIRED",
        },
        "records": [
            {
                "review_id": "LSR-014",
                "question": reviewed.get("LSR-014", {}).get("question"),
                "root_cause": "SOURCE_BODY_MISSING",
                "finding": "V2.5 only contains a registration/index page that names the PDF; the PDF body is absent from the frozen candidate staging corpus.",
                "registration_only_matches": len(registration),
                "exact_body_matches_in_v2_5_staging": len(exact_name),
                "physical_source": _parse_target(target),
                "expected_evidence": [
                    "\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a\u2018\u611f\u77e5\u91c7\u96c6\u5c42\u2014\u6570\u636e\u4e2d\u53f0\u5c42\u2014\u4e1a\u52a1\u5e94\u7528\u5c42\u2019\u4e09\u5c42\u67b6\u6784\u4f53\u7cfb\u3002",
                    "\u5728\u300a\u4e2d\u5efa\u96c6\u56e2\u667a\u80fd\u5efa\u90202035\u603b\u4f53\u884c\u52a8\u89c4\u5212\u300b\u6307\u5f15\u4e0b\u7f16\u5236\u3002",
                    "\u4f9d\u62588\u4e2aBIM\u793a\u8303\u9879\u76ee\u30014\u4e2a\u667a\u80fd\u5efa\u9020\u793a\u8303\u9879\u76ee\u68b3\u7406\u6570\u5b57\u5316\u9700\u6c42\uff1b\u4ee5\u5149\u8c37\u5143\u8457\u9879\u76ee\u4e3a\u5b9e\u8df5\u8f7d\u4f53\u3002",
                ],
                "remediation": "Ingest the real PDF as a V2.6.1_DEV_REMEDIATION source, then replay Q74; do not rewrite frozen V2.5.",
            },
            {
                "review_id": "LSR-017",
                "question": reviewed.get("LSR-017", {}).get("question"),
                "root_cause": "TEMPORAL_SCOPE_COLLISION",
                "finding": "The query specifies 2025 H1, but conflict detection groups H1 3.31% with full-year 3.33% because the plan has year but no period scope.",
                "source_context": metric_contexts,
                "expected_evidence": "2025 H1 overall efficiency is 3.31%.",
                "remediation": "Add H1/FULL_YEAR period scope to query plans and evidence; compare numeric facts only inside the same period, while retaining conflicts for period-unspecified queries.",
            },
        ],
    }


def main() -> int:
    payload = _diagnosis()
    out = V26 / "live_shadow_remediation_diagnosis.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# V2.6 Live Shadow Lost Hit Root-Cause Diagnosis",
        "",
        f"- Captured: `{payload['captured_at']}`",
        "- Boundary: frozen V2.5 unchanged; 8000 untouched; 8010 not switched.",
        "",
    ]
    for record in payload["records"]:
        lines += [
            f"## {record['review_id']}",
            "",
            f"- Root cause: `{record['root_cause']}`",
            f"- Finding: {record['finding']}",
            f"- Remediation: {record['remediation']}",
            "",
        ]
        if record["review_id"] == "LSR-014":
            source = record["physical_source"]
            lines.append(f"- Physical source: `{source['path']}`; exists=`{source['physical_exists']}`; parse=`{source.get('parse_status')}`; SHA-256=`{source.get('sha256')}`.")
        else:
            lines.append("- Scope: H1=3.31%; full year=3.33%; these are different periods and must not be treated as a same-period conflict.")
        lines.append("")
    (ROOT / "docs" / "LIVE_SHADOW_REMEDIATION_DIAGNOSIS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
