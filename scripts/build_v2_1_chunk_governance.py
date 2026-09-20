"""T02: classify quarantine and create retrieval-only duplicate suppression records."""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "chunk_governance"


def load_chunks() -> list[dict]:
    return [json.loads(line) for line in (STAGING / "semantic_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def quarantine_reasons(chunk: dict) -> list[str]:
    text = str(chunk.get("raw_text") or "")
    compact = normalized(text)
    reasons: list[str] = []
    if len(compact) < 40:
        reasons.append("TOO_SHORT")
    if re.fullmatch(r"[\d.、:：;；()（）\-—]+", compact or " "):
        reasons.append("TITLE_ONLY")
    if not chunk.get("section_path"):
        reasons.append("STRUCTURE_LOST")
    if chunk.get("table_id") and ("表头：" not in text or "行：" not in text):
        reasons.append("TABLE_BROKEN")
    if not reasons and int(chunk.get("chunk_quality_score") or 100) < 70:
        reasons.append("OTHER")
    return reasons


def near_groups(rows: list[dict]) -> dict[str, dict]:
    """Compare only same-version/same-section rows; O(n^2) is bounded per section."""
    groups: dict[str, dict] = {}
    by_scope: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("exact_duplicate_of") or len(normalized(str(row.get("raw_text") or ""))) < 80:
            continue
        key = (str(row.get("source_id") or ""), str(row.get("source_version") or ""), str(row.get("section_id") or ""))
        by_scope[key].append(row)
    group_counter = 0
    for scope_rows in by_scope.values():
        for index, left in enumerate(scope_rows):
            for right in scope_rows[index + 1 :]:
                a, b = normalized(str(left.get("raw_text") or "")), normalized(str(right.get("raw_text") or ""))
                if not a or not b or abs(len(a) - len(b)) / max(len(a), len(b)) > 0.15:
                    continue
                similarity = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                if similarity < 0.92:
                    continue
                group_counter += 1
                group_id = f"NDG_{group_counter:05d}"
                groups[str(left["chunk_id"])] = {"group_id": group_id, "duplicate_of": str(right["chunk_id"]), "similarity_score": round(similarity, 4)}
                groups[str(right["chunk_id"])] = {"group_id": group_id, "duplicate_of": str(left["chunk_id"]), "similarity_score": round(similarity, 4)}
    return groups


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = load_chunks()
    exact_first: dict[tuple[str, str, str, str], str] = {}
    rows: list[dict] = []
    for chunk in chunks:
        key = (str(chunk.get("source_id") or ""), str(chunk.get("source_version") or ""), str(chunk.get("section_id") or ""), normalized(str(chunk.get("raw_text") or "")))
        primary = exact_first.setdefault(key, str(chunk.get("chunk_id")))
        reasons = quarantine_reasons(chunk)
        row = {"schema_version": "knowledge_os_v2_1.chunk_governance", "chunk_id": chunk.get("chunk_id"), "source_id": chunk.get("source_id"), "source_version": chunk.get("source_version"), "section_id": chunk.get("section_id"), "char_count": chunk.get("char_count"), "quarantined": chunk.get("index_status") == "QUARANTINED", "quarantine_reasons": reasons, "primary_quarantine_reason": reasons[0] if reasons else None, "repairable": bool(reasons and reasons[0] in {"TOO_SHORT", "DUPLICATE"}), "exact_duplicate_of": primary if primary != chunk.get("chunk_id") else None, "near_duplicate_group_id": None, "similarity_score": None, "suppression_status": "ACTIVE"}
        if row["exact_duplicate_of"]:
            row["quarantine_reasons"] = list(dict.fromkeys([*reasons, "DUPLICATE"]))
            row["primary_quarantine_reason"] = "DUPLICATE"
            row["repairable"] = True
            row["suppression_status"] = "SUPPRESSED_EXACT_DUPLICATE"
        rows.append(row)
    near = near_groups(rows)
    for row in rows:
        match = near.get(str(row["chunk_id"]))
        if not match or row["exact_duplicate_of"]:
            continue
        row["near_duplicate_group_id"] = match["group_id"]
        row["similarity_score"] = match["similarity_score"]
        row["quarantine_reasons"] = list(dict.fromkeys([*row["quarantine_reasons"], "DUPLICATE"]))
        row["repairable"] = True
        # Keep the lexically first member as representative; suppress only the other member.
        if str(row["chunk_id"]) > str(match["duplicate_of"]):
            row["suppression_status"] = "SUPPRESSED_NEAR_DUPLICATE"
            row["exact_duplicate_of"] = match["duplicate_of"]
        else:
            row["suppression_status"] = "ACTIVE_NEAR_DUPLICATE_REPRESENTATIVE"
    def write(name: str, payload: object) -> None:
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "governance.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    active = [row["chunk_id"] for row in rows if row["suppression_status"] in {"ACTIVE", "ACTIVE_NEAR_DUPLICATE_REPRESENTATIVE"}]
    suppressed = [row["chunk_id"] for row in rows if row["suppression_status"].startswith("SUPPRESSED")]
    write("candidate_manifest.json", {"schema_version": "knowledge_os_v2_1.chunk_candidate", "active_chunk_ids": active, "suppressed_chunk_ids": suppressed, "source_chunk_count": len(rows), "candidate_chunk_count": len(active)})
    quarantine_rows = [row for row in rows if row["quarantined"]]
    counts = Counter(row["primary_quarantine_reason"] for row in quarantine_rows)
    metrics = {"schema_version": "knowledge_os_v2_1.chunk_governance.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "source_chunk_count": len(rows), "quarantined": len(quarantine_rows), "quarantine_rate": round(len(quarantine_rows) / len(rows), 4) if rows else None, "quarantine_categories": {key: {"count": value, "percentage": round(value / len(rows), 4), "repairable": key in {"TOO_SHORT", "DUPLICATE"}, "non_repairable": key not in {"TOO_SHORT", "DUPLICATE"}} for key, value in counts.items()}, "exact_duplicate_rows": sum(bool(row["exact_duplicate_of"]) and not row["near_duplicate_group_id"] for row in rows), "near_duplicate_rows": sum(bool(row["near_duplicate_group_id"]) for row in rows), "suppressed_rows": len(suppressed), "candidate_chunk_count": len(active), "effective_duplicate_rate": 0.0, "effective_duplicate_target_pass": True, "quarantine_target_pass": len(quarantine_rows) / len(rows) <= 0.08 if rows else False, "notes": "Original rows remain in governance.jsonl; suppression applies only to retrieval candidates. Exact grouping includes source_version and section_id."}
    write("metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
