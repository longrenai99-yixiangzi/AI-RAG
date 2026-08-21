from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    parser.add_argument(
        "--manifest",
        type=Path,
        help="仅处理 JSON 清单中的资料路径；路径必须位于 Vault 内。",
    )
    parser.add_argument(
        "--lexical-only",
        action="store_true",
        help="跳过 BGE-M3 向量化，只发布 SQLite + BM25 + Metadata 索引，供模型未就绪时验证。",
    )
    args = parser.parse_args()
    settings = Settings.load()
    file_paths = None
    source_aliases = None
    file_size_overrides = None
    if args.manifest:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        file_paths = []
        source_aliases = {}
        file_size_overrides = {}
        vault_root = settings.vault_root.resolve()
        allowed_roots = [vault_root, *(root.resolve() for root in settings.supplemental_roots)]
        for entry in payload.get("files", []):
            raw_path = entry.get("path") if isinstance(entry, dict) else entry
            alias = entry.get("source_path") if isinstance(entry, dict) else None
            path = Path(raw_path).resolve()
            try:
                if not any(path.is_relative_to(root) for root in allowed_roots):
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"manifest path is outside the configured source roots: {path}") from error
            if path.is_file():
                file_paths.append(path)
                if alias:
                    source_aliases[str(path)] = str(alias)
                if isinstance(entry, dict) and entry.get("max_file_size_mb"):
                    file_size_overrides[str(path)] = int(entry["max_file_size_mb"])
    report = index_vault(
        settings,
        EmbeddingService(settings),
        limit=args.limit,
        preflight=args.preflight,
        file_paths=file_paths,
        source_aliases=source_aliases,
        file_size_overrides=file_size_overrides,
        lexical_only=args.lexical_only,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
