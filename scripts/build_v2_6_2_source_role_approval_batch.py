from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
INPUT = V26 / "v2_6_2_source_gap_queue.json"
OUT = V26 / "v2_6_2_source_role_approval_batch.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    queue = json.loads(INPUT.read_text(encoding="utf-8"))
    source_questions: dict[str, set[str]] = defaultdict(set)
    metadata: dict[str, dict] = {}
    for item in queue.get("queue") or []:
        for source in item.get("sources") or []:
            path_text = str(source.get("source_path") or "")
            if not path_text or str(source.get("source_id") or "").startswith("V262-"):
                continue
            path = Path(path_text)
            source_questions[path_text].add(str(item.get("question_hash") or ""))
            metadata[path_text] = {"file_name": source.get("file_name") or path.name, "source_path": path_text, "physical_exists": path.exists()}
    records = []
    for path_text, hashes in sorted(source_questions.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        path = Path(path_text)
        records.append({
            **metadata[path_text],
            "question_count": len(hashes),
            "sha256": sha256(path) if path.is_file() else None,
            "approval_status": "PENDING_OWNER_APPROVAL",
            "approval_scope": "V2.6.2 source-role remediation only",
        })
    result = {
        "schema_version": "knowledge_os_v2_6_2.source_role_approval_batch",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": queue.get("candidate_hash"),
        "source_count": len(records),
        "all_physical_sources_exist": all(record["physical_exists"] for record in records),
        "approval_status": "PENDING_OWNER_APPROVAL",
        "owner_confirmation_text": "确认：批准本批次全部物理文件按当前 SHA-256 作为 V2.6.2 source-role remediation 有效内容版本；不授权写入或启动 8000。",
        "records": records,
        "formal_8000_touched": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidate_hash": result["candidate_hash"], "source_count": result["source_count"], "all_physical_sources_exist": result["all_physical_sources_exist"], "out": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
