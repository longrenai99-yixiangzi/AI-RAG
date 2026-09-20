"""T10 前置实验 - Chunk 重建对照实验（离线，不改运行时）。

假设：当前 Recall 低的主因是检索单元粒度不当
    section 层太粗（50.4% 文档只有 1–2 个 section）
    atomic 层太碎（平均 41 字符）

实验：把 atomic evidence 按文档顺序合并为带标题上下文的语义块，
      用**同一批问题、同一套 BM25、同一 ground truth** 重测 Recall，
      与现有 section 级检索对照。

若实验组显著高于基线，则证明"切分粒度"是共享根因，为 T10 系统级修复提供依据；
若没有提升，则说明根因在别处，不能据此改代码。

输出：
    evaluation/knowledge_os_system_audit/t10/chunk_rebuild_ab.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t10"
ATOMIC_PATH = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
SECTION_DIR = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "section_index"
GOLD_PATH = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"

TARGET_CHARS = 400      # 目标块大小
MAX_CHARS = 800         # 硬上限
MIN_CHARS = 60          # 低于此值继续并入下一段

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def load_gold(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for q in data.get("questions") or []:
        files = [str(f).strip() for f in (q.get("expected_files") or []) if str(f).strip()]
        if q.get("question") and files:
            rows.append({"id": q.get("id"), "question": q["question"], "expected_files": files})
    return rows


def build_semantic_chunks() -> list[dict]:
    """把 atomic 行按文档顺序合并为带标题上下文的语义块。"""
    by_doc: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    with ATOMIC_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            did = rec.get("document_id") or "<none>"
            if did not in by_doc:
                order.append(did)
            by_doc[did].append(rec)

    chunks: list[dict] = []
    for did in order:
        recs = by_doc[did]
        buf: list[str] = []
        buf_len = 0
        heading = ""
        first = recs[0]

        def flush() -> None:
            nonlocal buf, buf_len
            text = "\n".join(buf).strip()
            if text:
                chunks.append(
                    {
                        "file_name": first.get("file_name") or "",
                        "source_path": first.get("source_path") or "",
                        "document_id": did,
                        "heading_path": heading,
                        "text": text,
                        # 检索文本：文件标题 + 章节标题 + 正文，保证上下文不丢
                        "search_text": " ".join(
                            [str(first.get("file_name") or ""), heading, text]
                        ).strip(),
                    }
                )
            buf = []
            buf_len = 0

        for rec in recs:
            text = str(rec.get("text") or "").strip()
            hp = str(rec.get("heading_path") or "").strip()
            # 遇到新的更高层标题，先切断，避免不同章节混在一块
            if hp and hp != heading and buf_len >= MIN_CHARS:
                flush()
                heading = hp
            elif hp and not heading:
                heading = hp
            if not text:
                continue
            buf.append(text)
            buf_len += len(text)
            if buf_len >= TARGET_CHARS or len("\n".join(buf)) > MAX_CHARS:
                flush()
        flush()
    return chunks


def evaluate(chunks: list[dict], texts: list[str], gold: list[dict], topk: int = 20) -> dict:
    from rank_bm25 import BM25Okapi

    from app.bm25 import tokenize

    corpus = [tokenize(t) or ["_empty_"] for t in texts]
    bm25 = BM25Okapi(corpus)

    ranks: list[int] = []
    for q in gold:
        expected = set(q["expected_files"])
        scores = bm25.get_scores(tokenize(q["question"]) or ["_empty_"])
        order = np.argsort(-scores)[:topk]
        hit = 0
        for pos, i in enumerate(order, start=1):
            if chunks[i].get("file_name") in expected:
                hit = pos
                break
        ranks.append(hit)

    return {
        "evaluated": len(ranks),
        "recall@5": round(sum(1 for r in ranks if 1 <= r <= 5) / len(ranks), 4),
        "recall@10": round(sum(1 for r in ranks if 1 <= r <= 10) / len(ranks), 4),
        "recall@20": round(sum(1 for r in ranks if 1 <= r <= 20) / len(ranks), 4),
        "mrr": round(sum(1.0 / r for r in ranks if r > 0) / len(ranks), 4),
        "miss": sum(1 for r in ranks if r == 0),
        "ranks": ranks,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    gold = load_gold(GOLD_PATH)
    print(f"[T10-AB] 问题数 {len(gold)}")

    # ---- 基线：现有 section 级检索 ----
    print("[T10-AB] 构建基线（现有 section 级）...")
    sec_records = [
        json.loads(l)
        for l in (SECTION_DIR / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    sec_texts = [str(r.get("section_search_text") or "") for r in sec_records]
    baseline = evaluate(sec_records, sec_texts, gold)
    print(
        f"  基线 R@5={baseline['recall@5']:.3f} R@10={baseline['recall@10']:.3f} "
        f"R@20={baseline['recall@20']:.3f} MRR={baseline['mrr']:.3f} miss={baseline['miss']}"
    )

    # ---- 实验组：重建后的语义块 ----
    print("[T10-AB] 构建语义块（atomic 合并，带标题上下文）...")
    chunks = build_semantic_chunks()
    texts = [c["search_text"] for c in chunks]
    avg_chars = sum(len(t) for t in texts) / max(1, len(texts))
    print(f"  语义块 {len(chunks)} 条，平均 {avg_chars:.1f} 字符")
    rebuilt = evaluate(chunks, texts, gold)
    print(
        f"  重建 R@5={rebuilt['recall@5']:.3f} R@10={rebuilt['recall@10']:.3f} "
        f"R@20={rebuilt['recall@20']:.3f} MRR={rebuilt['mrr']:.3f} miss={rebuilt['miss']}"
    )

    delta20 = rebuilt["recall@20"] - baseline["recall@20"]
    improvement = delta20 / baseline["recall@20"] if baseline["recall@20"] else 0.0
    conclusion = (
        "切分粒度是共享根因，重建可显著提升召回"
        if delta20 > 0.05
        else "切分重建未带来显著改善，根因需另寻"
    )

    payload = {
        "task": "T10_CHUNK_REBUILD_AB",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "method": "同一问题集 / 同一 BM25 / 同一 ground truth，仅替换检索单元",
        "note": "离线实验，未修改运行时索引",
        "baseline_section_level": {
            "chunk_count": len(sec_records),
            "avg_chars": round(sum(len(t) for t in sec_texts) / max(1, len(sec_texts)), 1),
            **{k: v for k, v in baseline.items() if k != "ranks"},
        },
        "rebuilt_semantic_chunks": {
            "chunk_count": len(chunks),
            "avg_chars": round(avg_chars, 1),
            "target_chars": TARGET_CHARS,
            **{k: v for k, v in rebuilt.items() if k != "ranks"},
        },
        "delta": {
            "recall@20": round(delta20, 4),
            "relative_improvement": round(improvement, 4),
        },
        "conclusion": conclusion,
        "per_question": [
            {
                "question_id": q["id"],
                "question": q["question"],
                "baseline_rank": baseline["ranks"][i],
                "rebuilt_rank": rebuilt["ranks"][i],
            }
            for i, q in enumerate(gold)
        ],
    }
    (OUT / "chunk_rebuild_ab.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"[T10-AB] Recall@20: {baseline['recall@20']:.3f} -> {rebuilt['recall@20']:.3f} "
          f"(+{delta20:.3f}, 相对 +{improvement:.1%})")
    print(f"[T10-AB] 结论: {conclusion}")
    print(f"[T10-AB] 输出: {OUT / 'chunk_rebuild_ab.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
