from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.parsers import iter_source_files


EXTENSION_QUOTA = {".md": 10, ".pdf": 3, ".docx": 3, ".xlsx": 2, ".pptx": 2}
KEYWORDS = ("EPC", "3262", "设计", "策划", "计划", "评审", "质量", "价值", "检查", "案例")


def _score(path: Path) -> tuple[int, str]:
    name = path.name.casefold()
    return (sum(name.count(keyword.casefold()) for keyword in KEYWORDS), str(path).casefold())


def main() -> None:
    settings = Settings.load()
    scan_errors: list[str] = []
    paths = iter_source_files(settings.vault_root, scan_errors=scan_errors)
    by_type: dict[str, list[Path]] = {}
    for path in paths:
        by_type.setdefault(path.suffix.lower(), []).append(path)
    selected: list[Path] = []
    for extension, quota in EXTENSION_QUOTA.items():
        selected.extend(sorted(by_type.get(extension, []), key=_score, reverse=True)[:quota])
    if len(selected) < 20:
        remaining = [path for path in paths if path not in selected]
        selected.extend(sorted(remaining, key=_score, reverse=True)[: 20 - len(selected)])
    selected = selected[:20]
    settings.ensure_runtime_directories()
    output = settings.report_root / f"sample-manifest-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    payload = {
        "vault": str(settings.vault_root),
        "files": [str(path) for path in selected],
        "file_types": dict(Counter(path.suffix.lower() for path in selected)),
        "scan_errors": scan_errors,
        "selection": "format quotas plus filename keyword score; read-only",
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(output), "files": len(selected), "file_types": payload["file_types"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
