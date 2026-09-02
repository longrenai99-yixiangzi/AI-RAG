from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trial.config import TrialConfig
from app.trial.read_only_guard import check_trial_readiness


def main() -> int:
    result = check_trial_readiness(TrialConfig.load())
    print("TRIAL READINESS CHECK")
    for name, passed in result["checks"].items():
        print(f"{name} = {'true' if passed else 'false'}")
    print(f"Provider Budget status = {result['provider_budget'].get('status')}")
    print(f"Circuit state = {result['circuit_state']}")
    print(f"Status = {result['status']}")
    if result["blocked_reasons"]:
        print("Blocked reasons:")
        for reason in result["blocked_reasons"]:
            print(f"- {reason}")
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
