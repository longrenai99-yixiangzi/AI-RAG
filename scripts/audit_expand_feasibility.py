"""扩源可行性验证：抽样解析 [LOCAL_PATH_REDACTED]�公司技术部，测单位耗时并估算全量成本。

目的：在投入数十小时索引之前，先用小样本回答三个问题
    1. 现有 pipeline 能不能解析这些新文件？成功率多少？
    2. 单个文件平均耗时多少？全量 10347 个文件需要多久？
    3. OCR 是否可用？扫描件能否被识别？

只读操作：不写入任何索引，不修改运行配置。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "expand"

TEXT_EXT = {".docx", ".pdf", ".xlsx", ".pptx", ".doc", ".xls", ".md", ".txt", ".ppt"}
MAX_FILE_MB = 50


def collect(root: Path) -> dict[str, list[Path]]:
    by_type: dict[str, list[Path]] = defaultdict(list)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith((".", "~"))]
        for f in fn:
            if f.startswith(("~$", ".")):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in TEXT_EXT:
                continue
            p = Path(dp) / f
            try:
                if p.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                    continue
            except OSError:
                continue
            by_type[ext].append(p)
    return by_type


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(r"[LOCAL_PATH_REDACTED]�公司技术部"))
    parser.add_argument("--per-type", type=int, default=4, help="每种类型抽样数量")
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)

    if not args.root.is_dir():
        print(f"目录不存在: {args.root}")
        return 1

    print(f"[可行性] 扫描 {args.root} ...")
    by_type = collect(args.root)
    total_files = sum(len(v) for v in by_type.values())
    total_bytes = sum(p.stat().st_size for v in by_type.values() for p in v)
    print(f"  可索引文件 {total_files} 个，合计 {total_bytes / 1024**3:.2f} GB（已排除 >{MAX_FILE_MB}MB）")

    # OCR 依赖检查
    ocr_status = {}
    for mod, name in (("pytesseract", "pytesseract"), ("fitz", "PyMuPDF"), ("pdfplumber", "pdfplumber")):
        try:
            __import__(mod)
            ocr_status[name] = "AVAILABLE"
        except Exception as exc:
            ocr_status[name] = f"MISSING({type(exc).__name__})"
    print(f"  依赖检查: {ocr_status}")

    from app.ingestion.pipeline import run_document_pipeline

    samples: list[Path] = []
    for ext, paths in sorted(by_type.items(), key=lambda x: -len(x[1])):
        picks = random.sample(paths, min(args.per_type, len(paths)))
        samples.extend(picks)
        print(f"  {ext:<8} 共 {len(paths):>5} 个，抽样 {len(picks)} 个")

    results = []
    print(f"\n[可行性] 开始解析 {len(samples)} 个样本 ...")
    for p in samples:
        started = time.perf_counter()
        try:
            # 签名：run_document_pipeline(root, files=[...]) -> PipelineResult
            result = run_document_pipeline(p.parent, files=[p])
            elapsed = time.perf_counter() - started
            docs = list(getattr(result, "documents", []) or [])
            blocks = [b for d in docs for b in (getattr(d, "source_blocks", []) or [])]
            chunks = [c for d in docs for c in (getattr(d, "chunks", []) or [])]
            text = " ".join(str(getattr(c, "text", "") or "") for c in chunks) or " ".join(
                str(getattr(b, "text", "") or "") for b in blocks
            )
            results.append(
                {
                    "file": str(p),
                    "ext": p.suffix.lower(),
                    "size_mb": round(p.stat().st_size / 1024**2, 2),
                    "elapsed_s": round(elapsed, 3),
                    "status": "OK",
                    "block_count": len(blocks),
                    "chunk_count": len(chunks),
                    "chars": len(text),
                    "error": None,
                }
            )
            print(
                f"  OK   {p.suffix:<6} {p.stat().st_size / 1024**2:>7.2f}MB "
                f"{elapsed:>6.2f}s  chunks={len(chunks):<4} chars={len(text)}"
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            results.append(
                {
                    "file": str(p),
                    "ext": p.suffix.lower(),
                    "size_mb": round(p.stat().st_size / 1024**2, 2),
                    "elapsed_s": round(elapsed, 3),
                    "status": "FAILED",
                    "block_count": 0,
                    "chars": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                }
            )
            print(f"  FAIL {p.suffix:<6} {elapsed:>6.2f}s  {type(exc).__name__}: {str(exc)[:60]}")

    ok = [r for r in results if r["status"] == "OK"]
    failed = [r for r in results if r["status"] == "FAILED"]
    empty = [r for r in ok if r["chars"] == 0]

    # 按类型估算全量耗时（用该类型样本的平均耗时）
    per_type_elapsed: dict[str, list[float]] = defaultdict(list)
    per_type_chars: dict[str, list[int]] = defaultdict(list)
    for r in results:
        per_type_elapsed[r["ext"]].append(r["elapsed_s"])
        per_type_chars[r["ext"]].append(r["chars"])

    estimates = {}
    total_est_seconds = 0.0
    total_est_chars = 0
    for ext, paths in by_type.items():
        samples_elapsed = per_type_elapsed.get(ext) or []
        samples_chars = per_type_chars.get(ext) or []
        avg_elapsed = sum(samples_elapsed) / len(samples_elapsed) if samples_elapsed else 0.0
        avg_chars = sum(samples_chars) / len(samples_chars) if samples_chars else 0
        est = avg_elapsed * len(paths)
        estimates[ext] = {
            "files": len(paths),
            "avg_elapsed_s": round(avg_elapsed, 3),
            "avg_chars": int(avg_chars),
            "estimated_parse_hours": round(est / 3600, 2),
        }
        total_est_seconds += est
        total_est_chars += int(avg_chars * len(paths))

    payload = {
        "task": "EXPAND_FEASIBILITY",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "root": str(args.root),
        "max_file_mb": MAX_FILE_MB,
        "corpus": {
            "indexable_files": total_files,
            "indexable_gb": round(total_bytes / 1024**3, 2),
            "by_type": {k: len(v) for k, v in sorted(by_type.items(), key=lambda x: -len(x[1]))},
        },
        "dependency_check": ocr_status,
        "sample": {
            "count": len(results),
            "ok": len(ok),
            "failed": len(failed),
            "empty_extraction": len(empty),
            "success_rate": round(len(ok) / len(results), 4) if results else 0,
        },
        "parse_estimates_by_type": estimates,
        "total_estimated_parse_hours": round(total_est_seconds / 3600, 2),
        "total_estimated_chars": total_est_chars,
        "results": results,
        "failures": failed,
        "empty_extractions": [
            {"file": r["file"], "ext": r["ext"], "size_mb": r["size_mb"]} for r in empty
        ],
    }
    (OUT / "feasibility.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(f"[可行性] 样本 {len(results)} 个：成功 {len(ok)}，失败 {len(failed)}，"
          f"提取为空 {len(empty)}")
    print(f"[可行性] 全量解析预估：{payload['total_estimated_parse_hours']:.1f} 小时"
          f"（不含 embedding）")
    print(f"[可行性] 预估产出正文：{total_est_chars / 1e6:.1f} 百万字符")
    print(f"[可行性] 输出: {OUT / 'feasibility.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
