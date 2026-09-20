#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断 130 题「检索未命中」到底是「库里没有」还是「有但没排上来」。

做法：直接读 Qdrant shadow collection 的 payload（不跑稠密模型），看每题的期望
来源文件是否存在于索引语料中。

用法（在项目目录下）：
    .venv\\Scripts\\python.exe scripts\\trial_qa_corpus_coverage.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client import QdrantClient

from scripts.validate_unified_shadow_business import ROOT_CONFIG

BENCHMARK = PROJECT_ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl"


def iter_payloads(client: QdrantClient, collection: str):
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, limit=2048, offset=offset, with_payload=True, with_vectors=False
        )
        for point in points:
            yield point.payload or {}
        if offset is None:
            break


def main() -> int:
    rows = [json.loads(line) for line in BENCHMARK.read_text(encoding="utf-8").splitlines() if line.strip()]

    corpus_by_root: dict[str, set[str]] = {}
    for root_id, config in ROOT_CONFIG.items():
        shadow_dir = Path(config["shadow_dir"])
        if not shadow_dir.exists():
            print(f"[warn] missing shadow dir for {root_id}: {shadow_dir}")
            corpus_by_root[root_id] = set()
            continue
        client = QdrantClient(path=str(shadow_dir))
        try:
            names: set[str] = set()
            payloads = list(iter_payloads(client, config["collection"]))
            for payload in payloads:
                for key in ("file_name", "source_path"):
                    value = payload.get(key)
                    if value:
                        names.add(Path(str(value).replace("\\", "/")).name)
                        names.add(Path(str(value).replace("\\", "/")).stem)
            corpus_by_root[root_id] = names
            print(f"{root_id}: {len(payloads)} chunks, {len(names)} distinct file names  ({config['collection']})")
        finally:
            client.close()

    all_names = set().union(*corpus_by_root.values()) if corpus_by_root else set()

    present, absent, unknown = [], [], []
    for row in rows:
        basenames = [name for name in row.get("expected_source_basenames") or [] if name]
        if not basenames:
            unknown.append(row)
            continue
        hits = [name for name in basenames if name in all_names or any(name in candidate for candidate in all_names)]
        if hits:
            present.append((row, hits))
        else:
            absent.append((row, basenames))

    print()
    print("=" * 72)
    print(f"questions                     : {len(rows)}")
    print(f"expected source present in idx: {len(present)}")
    print(f"expected source ABSENT in idx : {len(absent)}")
    print(f"no parseable expected source  : {len(unknown)}")
    print()
    print("按册统计「期望来源不在索引中」：")
    print(dict(Counter(row["volume"] for row, _ in absent)))
    print()
    print("### 期望来源不在索引语料中的题目（属于「库里没有/未建索引」，不是排序问题）")
    for row, basenames in absent[:40]:
        print(f"  {row['question_id']} | {row['question'][:34]} | 期望: {','.join(basenames)[:60]}")

    out = PROJECT_ROOT / "evaluation" / "trial_qa_benchmark" / "corpus_coverage.json"
    out.write_text(
        json.dumps(
            {
                "corpus_file_names_by_root": {k: sorted(v) for k, v in corpus_by_root.items()},
                "present": [row["question_id"] for row, _ in present],
                "absent": [{"qid": row["question_id"], "question": row["question"], "expected": basenames} for row, basenames in absent],
                "no_expected_source": [row["question_id"] for row in unknown],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print()
    print(f"detail -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
