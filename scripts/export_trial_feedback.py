from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trial.config import TrialConfig
from app.trial.main import feedback_summary


def main() -> int:
    output = PROJECT_ROOT / "evaluation" / "internal_trial" / "trial_feedback_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(feedback_summary(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
