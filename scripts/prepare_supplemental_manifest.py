from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


SOURCES = [
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        # The original legacy .doc is kept untouched in [LOCAL_PATH_REDACTED]
        # .docx is a read-only conversion used only because the parser handles .docx.
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
        "source_path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
    {
        "path": Path(r"[LOCAL_PATH_REDACTED]"),
    },
]


def main() -> None:
    settings = Settings.load()
    allowed = tuple(root.resolve() for root in settings.supplemental_roots)
    entries = []
    for item in SOURCES:
        path = item["path"]
        resolved = path.resolve()
        if not resolved.is_file() or not any(resolved.is_relative_to(root) for root in allowed):
            raise FileNotFoundError(f"supplemental source is missing or outside allowlist: {path}")
        entry = {
            "path": str(resolved),
            "source_path": str(item.get("source_path", resolved)),
        }
        if resolved.suffix.lower() == ".xlsx":
            entry["max_file_size_mb"] = 512
        entries.append(entry)
    settings.ensure_runtime_directories()
    output = settings.report_root / "supplemental-manifest.json"
    output.write_text(
        json.dumps({"source_policy": "read-only supplemental sources", "files": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
