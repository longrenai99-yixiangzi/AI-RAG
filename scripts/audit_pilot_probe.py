"""T11 — 试点子集（2026 + EPC）入库前探针。

目的（只读，不写任何索引）：
1. 统计 PDF 是否带文本层 —— 决定 OCR 是否必须开启。
2. 抽样走真实解析管线 —— 估算 chunks 总数与 CPU 嵌入工时。
3. 统计解析产物质量 —— 复现旧知识根的「66% 文档 <500 字符」问题是否依然存在。

只读：不写入 data/shadow 任何生产目录，仅输出报告到 evaluation/。
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from app.parsers import SUPPORTED_EXTENSIONS, iter_source_files  # noqa: E402

BASE = Path(r"[LOCAL_PATH_REDACTED]�公司技术部")
SUBS = ["2026", "EPC"]
OUT_DIR = ROOT / "evaluation" / "knowledge_os_system_audit" / "t11_pilot"
PDF_SAMPLE = 80
PARSE_SAMPLE = 40
RANDOM_SEED = 20260910


def _collect() -> list[Path]:
    files: list[Path] = []
    for sub in SUBS:
        files.extend(iter_source_files(BASE / sub))
    return sorted({Path(p) for p in files}, key=lambda p: str(p).casefold())


def probe_pdf_text_layer(paths: list[Path]) -> dict:
    """采样 PDF，判断是否存在文本层。"""
    pdfs = [p for p in paths if p.suffix.casefold() == ".pdf"]
    random.Random(RANDOM_SEED).shuffle(pdfs)
    sample = pdfs[:PDF_SAMPLE]
    buckets = {"TEXT_LAYER_OK": 0, "EMPTY_OR_SCANNED": 0, "READ_ERROR": 0}
    chars_per_page: list[int] = []
    empty_examples: list[dict] = []
    started = time.perf_counter()
    for path in sample:
        try:
            with pymupdf.open(str(path)) as doc:
                pages = min(3, doc.page_count)
                text = "".join(doc.load_page(i).get_text() or "" for i in range(pages))
        except Exception as error:  # noqa: BLE001
            buckets["READ_ERROR"] += 1
            empty_examples.append({"source_path": str(path), "reason": f"{type(error).__name__}: {error}"})
            continue
        chars = len(text.strip())
        chars_per_page.append(chars // max(1, pages))
        if chars >= 100:
            buckets["TEXT_LAYER_OK"] += 1
        else:
            buckets["EMPTY_OR_SCANNED"] += 1
            if len(empty_examples) < 15:
                empty_examples.append(
                    {
                        "source_path": str(path),
                        "chars_first_pages": chars,
                        "page_count": pages,
                        "size_mb": round(path.stat().st_size / 1024**2, 2),
                    }
                )
    total = max(1, len(sample))
    return {
        "pdf_total": len(pdfs),
        "pdf_sampled": len(sample),
        "buckets": buckets,
        "text_layer_ratio": round(buckets["TEXT_LAYER_OK"] / total, 4),
        "median_chars_per_page": statistics.median(chars_per_page) if chars_per_page else 0,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "empty_examples": empty_examples,
    }


def probe_parse_yield(paths: list[Path]) -> dict:
    """抽样走真实解析管线，估算 chunks 规模与文档质量。"""
    from app.ingestion.pipeline import run_document_pipeline

    by_ext: dict[str, list[Path]] = {}
    for path in paths:
        by_ext.setdefault(path.suffix.casefold(), []).append(path)
    rng = random.Random(RANDOM_SEED)
    sample: list[Path] = []
    for ext, group in sorted(by_ext.items()):
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        rng.shuffle(group)
        share = max(6, round(PARSE_SAMPLE * len(group) / len(paths)))
        sample.extend(group[:share])
    sample = sorted({Path(p) for p in sample}, key=lambda p: str(p).casefold())

    per_file: list[dict] = []
    started = time.perf_counter()
    for path in sample:
        item = {"source_path": str(path), "ext": path.suffix.casefold(), "status": "OK", "chars": 0, "chunks": 0, "error": ""}
        try:
            result = run_document_pipeline(path.parent, files=[path])
            chunks = [c for d in result.documents for c in d.chunks]
            item["chars"] = sum(len(c.text or "") for c in chunks)
            item["chunks"] = len(chunks)
            if item["chars"] == 0:
                item["status"] = "EMPTY"
        except Exception as error:  # noqa: BLE001
            item["status"] = "ERROR"
            item["error"] = f"{type(error).__name__}: {error}"
        per_file.append(item)
    elapsed = time.perf_counter() - started

    ok = [i for i in per_file if i["status"] == "OK"]
    empty = [i for i in per_file if i["status"] == "EMPTY"]
    errors = [i for i in per_file if i["status"] == "ERROR"]
    chunks_list = [i["chunks"] for i in per_file]
    chars_list = [i["chars"] for i in per_file]
    avg_chunks = statistics.mean(chunks_list) if chunks_list else 0.0
    avg_chars = statistics.mean(chars_list) if chars_list else 0.0
    # 文档级字符量的分布：复现旧根「66% 文档 <500 字符」口径
    short_ratio = round(sum(1 for c in chars_list if c < 500) / max(1, len(chars_list)), 4)
    return {
        "sampled": len(per_file),
        "ok": len(ok),
        "empty": len(empty),
        "error": len(errors),
        "avg_chunks_per_file": round(avg_chunks, 2),
        "avg_chars_per_file": round(avg_chars, 1),
        "median_chars_per_file": statistics.median(chars_list) if chars_list else 0,
        "short_doc_ratio_lt_500_chars": short_ratio,
        "parse_seconds_per_file": round(elapsed / max(1, len(per_file)), 3),
        "estimated_total_chunks": round(avg_chunks * len(paths)),
        "estimated_parse_hours": round(elapsed / max(1, len(per_file)) * len(paths) / 3600, 2),
        "empty_examples": empty[:15],
        "error_examples": errors[:15],
        "per_file": per_file,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = _collect()
    ext_counter = Counter(p.suffix.casefold() for p in paths)
    size_by_ext: dict[str, int] = {}
    for path in paths:
        try:
            size_by_ext[path.suffix.casefold()] = size_by_ext.get(path.suffix.casefold(), 0) + path.stat().st_size
        except OSError:
            pass

    print(f"[probe] files={len(paths)}", flush=True)
    pdf_probe = probe_pdf_text_layer(paths)
    print(f"[probe] pdf done: {pdf_probe['buckets']}", flush=True)
    parse_probe = probe_parse_yield(paths)
    print(f"[probe] parse done: ok={parse_probe['ok']} empty={parse_probe['empty']} error={parse_probe['error']}", flush=True)

    report = {
        "schema_version": "pilot.probe.v1",
        "roots": [str(BASE / s) for s in SUBS],
        "file_count": len(paths),
        "extension_counts": dict(ext_counter),
        "size_bytes_by_ext": size_by_ext,
        "total_gb": round(sum(size_by_ext.values()) / 1024**3, 2),
        "pdf_text_layer": pdf_probe,
        "parse_yield": parse_probe,
    }
    (OUT_DIR / "pilot_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 试点子集入库前探针（2026 + EPC）",
        "",
        f"- 文件总数：**{len(paths)}**，总体积：**{report['total_gb']} GB**",
        f"- 扩展名分布：{', '.join(f'{k}={v}' for k, v in ext_counter.most_common())}",
        "",
        "## 1. PDF 文本层（决定 OCR 是否必须）",
        "",
        f"- PDF 总数 {pdf_probe['pdf_total']}，采样 {pdf_probe['pdf_sampled']}",
        f"- 有文本层：**{pdf_probe['buckets']['TEXT_LAYER_OK']}** / 疑似扫描件：{pdf_probe['buckets']['EMPTY_OR_SCANNED']} / 读取失败：{pdf_probe['buckets']['READ_ERROR']}",
        f"- 文本层占比：**{pdf_probe['text_layer_ratio']:.1%}**，每页中位字符数：{pdf_probe['median_chars_per_page']}",
        "",
        "## 2. 解析产出（决定嵌入工时）",
        "",
        f"- 抽样 {parse_probe['sampled']} 个：成功 {parse_probe['ok']} / 空 {parse_probe['empty']} / 异常 {parse_probe['error']}",
        f"- 平均每文件 {parse_probe['avg_chunks_per_file']} chunks、{parse_probe['avg_chars_per_file']} 字符（中位 {parse_probe['median_chars_per_file']}）",
        f"- **<500 字符的短文档占比：{parse_probe['short_doc_ratio_lt_500_chars']:.1%}**（旧知识根基线为 66%）",
        f"- 预估 chunks 总量：**{parse_probe['estimated_total_chunks']}**",
        f"- 预估解析耗时：{parse_probe['estimated_parse_hours']} 小时（不含嵌入）",
        "",
    ]
    (OUT_DIR / "PILOT_PROBE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"parse_yield"}}, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in parse_probe.items() if k != "per_file"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
