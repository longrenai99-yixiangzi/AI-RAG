from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


SOURCES = [
    Path(r"D:\工作\设计支持中心\局制度文件\《项目设计管理手册》.pdf"),
    Path(r"D:\工作\二公司技术部\2026\知识库\价值创造点清单\设计价值创造点清单0819.xlsx"),
]


def main() -> None:
    settings = Settings.load()
    allowed = tuple(root.resolve() for root in settings.supplemental_roots)
    entries = []
    for path in SOURCES:
        resolved = path.resolve()
        if not resolved.is_file() or not any(resolved.is_relative_to(root) for root in allowed):
            raise FileNotFoundError(f"supplemental source is missing or outside allowlist: {path}")
        entry = {"path": str(resolved), "source_path": str(resolved)}
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
