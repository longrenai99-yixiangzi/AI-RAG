from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


SOURCES = [
    {
        "path": Path(r"D:\工作\设计支持中心\局制度文件\《项目设计管理手册》.pdf"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\知识库\价值创造点清单\设计价值创造点清单0819.xlsx"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\设计复盘\EPC设计管理经验总结(葛店新华中学项目).docx"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\概算及策划评审\葛店新华中学\葛店新华中学-设计管理策划.docx"),
    },
    {
        # The original legacy .doc is kept untouched in D:\工作.  The project-local
        # .docx is a read-only conversion used only because the parser handles .docx.
        "path": Path(r"D:\AI设计管理知识库\data\supplemental\华中公司葛店新华中学EPC设计管理示范项目打造实施方案1.0.docx"),
        "source_path": Path(r"D:\工作\二公司技术部\2026\示范工程\实施方案\华中公司葛店新华中学EPC设计管理示范项目打造实施方案1.0.doc"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\示范工程\2026年公司示范工程计划1.docx"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\示范工程\关于发布2026年公司设计示范、深化设计示范、BIM示范工程（第一批）计划的通知.docx"),
    },
    {
        "path": Path(r"D:\工作\二公司技术部\2026\示范工程\2026年上半年公司EPC项目及设计示范项目检查情况通报.docx"),
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
