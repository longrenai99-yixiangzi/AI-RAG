from __future__ import annotations

import argparse
import json

from app.config import Settings
from app.embeddings import EmbeddingService
from app.indexer import index_vault


def main() -> None:
    def positive_number(value: str) -> int:
        number = int(value)
        if number < 1:
            raise argparse.ArgumentTypeError("--limit 必须大于 0")
        return number

    parser = argparse.ArgumentParser(
        description="Read-only index builder for the AI design-management vault."
    )
    parser.add_argument(
        "--limit",
        type=positive_number,
        help="仅索引排序后的前 N 个支持文件；用于首次演示，不改知识源。",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="只读解析并统计切片，不下载模型、不建立或替换索引。",
    )
    args = parser.parse_args()
    settings = Settings.load()
    report = index_vault(
        settings,
        EmbeddingService(settings),
        limit=args.limit,
        preflight=args.preflight,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
