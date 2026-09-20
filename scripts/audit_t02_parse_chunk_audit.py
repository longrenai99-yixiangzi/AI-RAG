"""T02 - 解析、结构化与 Chunk 质量审计（只读）。

对 Atomic Evidence 全量记录做可复现审计，输出：

    evaluation/knowledge_os_system_audit/t02/
        chunk_audit_summary.json     指标与错误码分布
        chunk_debug_view.jsonl       全量 Chunk 调试视图
        chunk_samples.json           随机抽样 + 各错误码样本（供人工复核）
        document_quality.json        文档级解析质量

判据全部显式定义，禁止事后调整以美化结果。
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t02"
ATOMIC_PATH = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
STATE_PATH = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"

# ---------- 判据阈值（审计前固定，不随结果调整） ----------
MIN_CHUNK_CHARS = 10      # 低于此长度视为无信息碎片
MAX_CHUNK_CHARS = 2000    # 高于此长度视为过长，影响检索定位
GARBLED_RATIO = 0.30      # 非法字符占比超过此值视为乱码
SAMPLE_SIZE = 240         # 随机抽样数量（任务书要求不少于 200）
PER_ERROR_SAMPLES = 15    # 每个错误码抽取的样本数
RANDOM_SEED = 20260909    # 固定种子，保证可复现

CJK = r"\u4e00-\u9fff\u3400-\u4dbf"
# 工程/数学/单位符号白名单，避免把 "6mm≤3㎡" 这类有效内容判为乱码
TECH_SYMBOLS = (
    "\u2264\u2265\u00b1\u00d7\u00f7\u2248\u2260\u2211\u221a"  # ≤ ≥ ± × ÷ ≈ ≠ ∑ √
    "\u33a1\u33a0\u33c3\u33d4\u00b0\u2103\u2109\u00b2\u00b3\u207f"  # ㎡ ㎠ ㏄ ㏔ ° ℃ ℉ ² ³ ⁿ
    "\u03b1-\u03c9\u0391-\u03a9"  # 希腊字母
)
ALLOWED_PATTERN = re.compile(
    rf"[0-9A-Za-z{CJK}{TECH_SYMBOLS}\s"
    r"\,\.\;\:\!\?\-\_\/\(\)\[\]\{\}\<\>\"'`~@#\$%\^&\*\+=\|\\"
    r"\u3000-\u303f\uff00-\uffef]"
)

TERMINATORS = "。！？；：.!?;:）)》」』\"'”’"


def is_garbled(text: str) -> bool:
    """乱码判据：出现替换字符，或合法字符占比低于阈值。"""
    if not text:
        return False
    if "\ufffd" in text:
        return True
    allowed = sum(1 for ch in text if ALLOWED_PATTERN.match(ch))
    return (1 - allowed / len(text)) > GARBLED_RATIO


def has_information(text: str) -> bool:
    """是否承载有效信息：至少包含一个中英文字符或数字。"""
    return bool(re.search(rf"[0-9A-Za-z{CJK}]", text))


def looks_like_list_fragment(text: str, heading_path: str | None) -> bool:
    """失去归属的列表项：以列表标记开头、过短、无章节标题，且不是完整结束的句子。

    有 heading_path 的列表项视为上下文可追溯，不计入；
    以终止符结尾的列表项视为语义完整，不计入。
    """
    if heading_path:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > 60:
        return False
    if stripped[-1] in TERMINATORS:
        return False
    return bool(re.match(r"^([-*•·]|\d+[.、)]|[（(]\d+[)）]|[一二三四五六七八九十]+[、.])", stripped))


def looks_dangling(text: str) -> bool:
    """疑似被切断的句子：不以任何终止标点或冒号结尾，且长度较长。"""
    stripped = text.rstrip()
    if not stripped or len(stripped) < 25:
        return False
    return stripped[-1] not in TERMINATORS


def small_subtype(text: str) -> str:
    """过短碎片的细分类型，用于解释 36% 碎片究竟是什么。"""
    s = text.strip()
    if not s:
        return "empty"
    if s.startswith("#"):
        return "markdown_heading"
    if re.match(r"^([-*•·]|\d+[.、)])", s):
        return "list_item"
    if re.fullmatch(r"[0-9\.\,\%\-\+\s/：:()（）]*", s):
        return "pure_number_or_symbol"
    if len(s) <= 4:
        return "ultra_short_label"
    return "short_fragment"


def classify(rec: dict) -> list[str]:
    """返回该 Chunk 命中的错误码列表（可多值）。"""
    codes: list[str] = []
    text = rec.get("text") or ""
    meta = rec.get("metadata") or {}
    granularity = rec.get("granularity")
    heading_path = rec.get("heading_path")
    n = len(text)

    if meta.get("parse_status") == "needs_ocr":
        codes.append("OCR_FAILED")
    if not text.strip():
        codes.append("CHUNK_MISSING")
        return codes
    if is_garbled(text):
        codes.append("PARSE_FAILED")
    if n < MIN_CHUNK_CHARS:
        codes.append("CHUNK_TOO_SMALL")
    if n > MAX_CHUNK_CHARS:
        codes.append("CHUNK_TOO_LARGE")
    if not heading_path and granularity not in ("paragraph",):
        codes.append("STRUCTURE_LOST")
    if granularity in ("row", "table_row") and not heading_path:
        codes.append("TABLE_CONTEXT_LOST")
    if granularity in ("row", "table_row") and not re.search(r"[:：]|[:：]", text) and not heading_path:
        codes.append("TABLE_CONTEXT_LOST")
    if looks_like_list_fragment(text, heading_path):
        codes.append("CHUNK_CONTEXT_MISSING")
    if granularity in ("paragraph", "page_line", "line") and looks_dangling(text):
        codes.append("CHUNK_CONTEXT_MISSING")
    return sorted(set(codes))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(RANDOM_SEED)

    # 来源版本映射，用于 Debug View
    source_version_map: dict[str, str] = {}
    source_id_map: dict[str, str] = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        for sid, src in state.get("sources", {}).items():
            path = src.get("source_path") or ""
            if path:
                source_id_map[path.lower()] = sid
                source_version_map[path.lower()] = src.get("current_hash") or ""

    total = 0
    by_type: dict[str, Counter] = defaultdict(Counter)
    by_granularity: dict[str, Counter] = defaultdict(Counter)
    error_counter: Counter = Counter()
    error_by_type: dict[str, Counter] = defaultdict(Counter)
    error_samples: dict[str, list] = defaultdict(list)
    length_by_type: dict[str, list] = defaultdict(list)
    small_subtype_counter: Counter = Counter()

    doc_stats: dict[str, dict] = {}

    text_seen: dict[tuple, int] = {}
    duplicate_records = 0
    duplicate_examples: list[dict] = []

    all_records: list[dict] = []

    reservoir: list[dict] = []

    with ATOMIC_PATH.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                error_counter["PARSE_FAILED"] += 1
                continue
            total += 1
            text = rec.get("text") or ""
            meta = rec.get("metadata") or {}
            ftype = rec.get("file_type") or "<none>"
            gran = rec.get("granularity") or "<none>"
            spath = rec.get("source_path") or ""
            by_type[ftype]["count"] += 1
            by_granularity[gran]["count"] += 1
            length_by_type[ftype].append(len(text))

            codes = classify(rec)
            if "CHUNK_TOO_SMALL" in codes:
                small_subtype_counter[small_subtype(text)] += 1
            for c in codes:
                error_counter[c] += 1
                error_by_type[ftype][c] += 1
                if len(error_samples[c]) < PER_ERROR_SAMPLES:
                    error_samples[c].append(
                        {
                            "evidence_id": rec.get("evidence_id"),
                            "file_type": ftype,
                            "granularity": gran,
                            "source_path": spath,
                            "heading_path": rec.get("heading_path"),
                            "location": rec.get("location"),
                            "text": text[:300],
                        }
                    )
            if codes:
                by_type[ftype]["error"] += 1
                by_granularity[gran]["error"] += 1

            # 重复检测：同一来源下完全相同的正文
            key = (spath, text.strip())
            if text.strip():
                if key in text_seen:
                    duplicate_records += 1
                    if len(duplicate_examples) < PER_ERROR_SAMPLES:
                        duplicate_examples.append(
                            {
                                "evidence_id": rec.get("evidence_id"),
                                "first_evidence_id": text_seen[key],
                                "file_type": ftype,
                                "source_path": spath,
                                "text": text[:200],
                            }
                        )
                else:
                    text_seen[key] = rec.get("evidence_id")
            if duplicate_records and "CHUNK_DUPLICATE" not in error_counter:
                pass

            # 文档级统计
            did = rec.get("document_id")
            ds = doc_stats.setdefault(
                did,
                {
                    "document_id": did,
                    "source_path": spath,
                    "file_name": rec.get("file_name"),
                    "file_type": ftype,
                    "evidence_count": 0,
                    "chars_total": 0,
                    "empty": 0,
                    "too_small": 0,
                    "no_heading": 0,
                    "garbled": 0,
                },
            )
            ds["evidence_count"] += 1
            ds["chars_total"] += len(text)
            if not text.strip():
                ds["empty"] += 1
            if len(text) < MIN_CHUNK_CHARS:
                ds["too_small"] += 1
            if not rec.get("heading_path"):
                ds["no_heading"] += 1
            if is_garbled(text):
                ds["garbled"] += 1

            # Debug View
            debug_rec = {
                "chunk_id": rec.get("evidence_id"),
                "source_id": source_id_map.get(spath.lower(), ""),
                "source_version": (source_version_map.get(spath.lower(), "") or "")[:16],
                "document_title": rec.get("file_name"),
                "page": (rec.get("location") or {}).get("page")
                or (rec.get("location") or {}).get("slide")
                or (rec.get("location") or {}).get("sheet"),
                "section": rec.get("heading_path"),
                "parent_section": (rec.get("heading_path") or "").split("/")[0] if rec.get("heading_path") else None,
                "knowledge_node": meta.get("board"),
                "granularity": gran,
                "file_type": ftype,
                "text": text,
                "metadata": {
                    "knowledge_type": meta.get("knowledge_type"),
                    "discipline": meta.get("discipline"),
                    "parse_status": meta.get("parse_status"),
                    "metadata_review_status": meta.get("metadata_review_status"),
                    "schema_version": meta.get("schema_version"),
                },
                "embedding_status": "UNKNOWN_NOT_TRACKED",
                "error_codes": codes,
                "too_small_subtype": small_subtype(text) if "CHUNK_TOO_SMALL" in codes else None,
            }
            all_records.append(debug_rec)

            # 蓄水池抽样
            if len(reservoir) < SAMPLE_SIZE:
                reservoir.append(debug_rec)
            else:
                j = random.randint(0, idx)
                if j < SAMPLE_SIZE:
                    reservoir[j] = debug_rec

    # ---------- 指标计算 ----------
    too_small = error_counter.get("CHUNK_TOO_SMALL", 0)
    too_large = error_counter.get("CHUNK_TOO_LARGE", 0)
    garbled = error_counter.get("PARSE_FAILED", 0)
    ocr = error_counter.get("OCR_FAILED", 0)
    structure_lost = error_counter.get("STRUCTURE_LOST", 0)
    table_context_lost = error_counter.get("TABLE_CONTEXT_LOST", 0)
    context_missing = error_counter.get("CHUNK_CONTEXT_MISSING", 0)

    table_total = sum(v["count"] for k, v in by_granularity.items() if k in ("row", "table_row"))
    clean = total - len(
        [
            1
            for r in all_records
            if set(r["error_codes"]) & {"PARSE_FAILED", "OCR_FAILED", "CHUNK_TOO_SMALL", "CHUNK_TOO_LARGE", "CHUNK_MISSING", "CHUNK_CONTEXT_MISSING"}
        ]
    )

    summary = {
        "task": "T02_PARSE_STRUCTURE_CHUNK_AUDIT",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_file": str(ATOMIC_PATH),
        "criteria": {
            "min_chunk_chars": MIN_CHUNK_CHARS,
            "max_chunk_chars": MAX_CHUNK_CHARS,
            "garbled_ratio": GARBLED_RATIO,
            "sample_size": SAMPLE_SIZE,
            "random_seed": RANDOM_SEED,
        },
        "total_records": total,
        "metrics": {
            "parse_success_rate": round((total - garbled - ocr) / total, 4) if total else 0,
            "structured_parse_rate": round((total - structure_lost) / total, 4) if total else 0,
            "chunk_integrity_rate": round(clean / total, 4) if total else 0,
            "table_context_preservation_rate": round(
                (table_total - table_context_lost) / table_total, 4
            )
            if table_total
            else None,
            "duplicate_chunk_rate": round(duplicate_records / total, 4) if total else 0,
            "avg_text_chars": round(
                sum(len(r["text"]) for r in all_records) / total, 2
            )
            if total
            else 0,
        },
        "error_code_distribution": dict(error_counter.most_common()),
        "error_rate_by_code": {
            k: round(v / total, 4) for k, v in error_counter.most_common()
        },
        "table_granularity_total": table_total,
        "too_small_subtype_distribution": dict(small_subtype_counter.most_common()),
        "by_file_type": {
            k: {
                "count": v["count"],
                "error_count": v.get("error", 0),
                "error_rate": round(v.get("error", 0) / v["count"], 4) if v["count"] else 0,
                "avg_chars": round(sum(length_by_type[k]) / len(length_by_type[k]), 2)
                if length_by_type[k]
                else 0,
                "error_breakdown": dict(error_by_type[k].most_common()),
            }
            for k, v in sorted(by_type.items(), key=lambda x: -x[1]["count"])
        },
        "by_granularity": {
            k: {
                "count": v["count"],
                "error_count": v.get("error", 0),
                "error_rate": round(v.get("error", 0) / v["count"], 4) if v["count"] else 0,
            }
            for k, v in sorted(by_granularity.items(), key=lambda x: -x[1]["count"])
        },
        "duplicate_records": duplicate_records,
        "duplicate_examples": duplicate_examples,
        "error_samples": {k: v for k, v in sorted(error_samples.items())},
    }

    (OUT / "chunk_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with (OUT / "chunk_debug_view.jsonl").open("w", encoding="utf-8") as fh:
        for r in all_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    (OUT / "chunk_samples.json").write_text(
        json.dumps(
            {"sample_size": len(reservoir), "seed": RANDOM_SEED, "samples": reservoir},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    docs = sorted(doc_stats.values(), key=lambda d: -d["evidence_count"])
    for d in docs:
        d["avg_chars"] = round(d["chars_total"] / d["evidence_count"], 2) if d["evidence_count"] else 0
        d["too_small_rate"] = round(d["too_small"] / d["evidence_count"], 4) if d["evidence_count"] else 0
        d["no_heading_rate"] = round(d["no_heading"] / d["evidence_count"], 4) if d["evidence_count"] else 0
    (OUT / "document_quality.json").write_text(
        json.dumps(
            {
                "document_count": len(docs),
                "documents_with_single_evidence": sum(1 for d in docs if d["evidence_count"] == 1),
                "documents": docs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    m = summary["metrics"]
    print("\n[T02] Chunk 质量审计结果")
    print(f"  记录总数            : {total}")
    print(f"  Parse Success Rate  : {m['parse_success_rate']:.2%}")
    print(f"  Structured Parse    : {m['structured_parse_rate']:.2%}")
    print(f"  Chunk Integrity     : {m['chunk_integrity_rate']:.2%}")
    print(f"  Table Context Pres. : {m['table_context_preservation_rate']}")
    print(f"  Duplicate Chunk Rate: {m['duplicate_chunk_rate']:.2%}")
    print(f"  平均字符数          : {m['avg_text_chars']}")
    print("  错误码分布          :")
    for k, v in summary["error_code_distribution"].items():
        print(f"      {k:<26} {v:>7}  ({v / total:.2%})")
    print(f"  输出目录            : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
