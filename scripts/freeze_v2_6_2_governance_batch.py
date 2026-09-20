from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
SOURCE = V26 / "v2_6_2_remaining_governance_proposal.json"


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    if payload.get("approval_status") != "APPROVED":
        raise RuntimeError("GOVERNANCE_BATCH_NOT_APPROVED")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else len(payload.get("records") or [])
    if len(payload.get("records") or []) != count:
        raise RuntimeError(f"GOVERNANCE_BATCH_EXPECTED_{count}_GOT_{len(payload.get('records') or [])}")
    target = V26 / f"v2_6_2_remaining_governance_proposal_approved_{count}.json"
    if target.exists():
        # Keep approval snapshots immutable; count-only names can collide across batches.
        target = V26 / f"v2_6_2_remaining_governance_proposal_approved_{count}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    payload["note"] = f"Immutable approval record for the {count}-file batch approved for V2.6.2 remediation only."
    for item in payload["records"]:
        item["approval_status"] = "APPROVED"
        item["approved_by"] = "USER_CONFIRMED"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "APPROVED", "source_count": len(payload["records"]), "out": str(target)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
