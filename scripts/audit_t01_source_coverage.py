"""T01 - Source Coverage 审计（只读）。

核心问题：用户问的问题，答案对应资料到底有没有进入知识库？
不能把"没召回"与"根本没有资料"混为一谈。

数据源：
    问题集     tests/gold_questions/full_corpus_gold_questions.yaml (expected_files)
    来源库     data/shadow/knowledge_os/state.json
    文档库     data/shadow/atomic_evidence/records.jsonl

输出：
    evaluation/knowledge_os_system_audit/t01/source_coverage.json
"""

from __future__ import annotations

import json
import re
from urllib.parse import unquote
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t01"
STATE_PATH = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
ATOMIC_PATH = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
GOLD_PATH = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"


def load_gold_questions(path: Path) -> list[dict]:
    """用 YAML 解析器加载问题集，避免正则解析 flow style 出错。"""
    if not path.exists():
        return []
    import yaml  # 项目 venv 已提供

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    questions = data.get("questions") or []
    normalized = []
    for q in questions:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        normalized.append(
            {
                "id": q.get("id"),
                "topic": q.get("topic"),
                "question": q.get("question"),
                "expected_files": list(q.get("expected_files") or []),
                "difficulty": q.get("difficulty"),
            }
        )
    return normalized


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    sources = state.get("sources", {})

    # 已登记来源：文件名 / 路径 / 状态
    registered_by_name: dict[str, dict] = {}
    registered_by_path: dict[str, dict] = {}
    for sid, src in sources.items():
        name = (src.get("file_name") or "").casefold()
        path = (src.get("source_path") or "").casefold()
        info = {
            "source_id": sid,
            "file_name": src.get("file_name"),
            "source_path": src.get("source_path"),
            "exists": src.get("exists"),
            "body_status": src.get("body_status"),
            "index_status": src.get("index_status"),
            "approval_status": src.get("approval_status"),
            "version_count": len(src.get("versions") or []),
            "active_versions": sum(1 for v in (src.get("versions") or []) if v.get("active")),
        }
        if name:
            registered_by_name.setdefault(name, info)
        if path:
            registered_by_path[path] = info

    # 实际入库文档（Atomic Evidence 中出现过的文件）
    docs: dict[str, dict] = {}
    with ATOMIC_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = (rec.get("file_name") or "").casefold()
            spath = rec.get("source_path") or ""
            d = docs.setdefault(
                name,
                {
                    "file_name": rec.get("file_name"),
                    "source_path": spath,
                    "file_type": rec.get("file_type"),
                    "evidence_count": 0,
                    "chars": 0,
                    "body_evidence_count": 0,
                    "body_chars": 0,
                    "linked_targets": set(),
                },
            )
            d["evidence_count"] += 1
            text = str(rec.get("text") or "")
            d["chars"] += len(text)
            fragment_chars = _body_fragment_chars(text)
            if fragment_chars:
                d["body_evidence_count"] += 1
                d["body_chars"] += fragment_chars
            for target in re.findall(r"file:///([^\r\n]+)", text):
                d["linked_targets"].add(unquote(target.strip().removesuffix(")")).replace("/", "\\"))

    questions = load_gold_questions(GOLD_PATH)
    rows = []
    code_counter: Counter = Counter()

    for q in questions:
        expected = q.get("expected_files") or []
        for fname in expected:
            key = fname.casefold()
            in_registry = key in registered_by_name
            in_index = key in docs
            reg = registered_by_name.get(key)
            doc = docs.get(key)
            targets = sorted((doc or {}).get("linked_targets", set()))
            linked_regs = [registered_by_path[target.casefold()] for target in targets if target.casefold() in registered_by_path]
            linked_indexed = any(item.get("index_status") == "INDEXED" for item in linked_regs)
            in_registry = in_registry or bool(linked_regs)

            codes: list[str] = []
            if not in_registry and not in_index:
                codes.append("SOURCE_MISSING")
            else:
                if reg and reg.get("exists") is False:
                    codes.append("SOURCE_MISSING")
                if reg and reg.get("index_status") != "INDEXED":
                    codes.append("SOURCE_DISABLED")
                if reg and reg.get("active_versions", 0) == 0:
                    codes.append("SOURCE_VERSION_ERROR")
                if reg and reg.get("active_versions", 0) > 1:
                    codes.append("SOURCE_VERSION_ERROR")
                if in_registry and not in_index:
                    codes.append("SOURCE_SCOPE_ERROR")
                if in_index and (doc or {}).get("body_chars", 0) < 80 and not linked_indexed:
                    codes.append("SOURCE_BODY_MISSING")
            if not codes:
                codes.append("OK")
            for c in codes:
                code_counter[c] += 1

            rows.append(
                {
                    "question_id": q.get("id"),
                    "topic": q.get("topic"),
                    "question": q.get("question"),
                    "expected_source": fname,
                    "expected_source_id": (reg or (linked_regs[0] if linked_regs else {})).get("source_id"),
                    "source_exists": bool(reg and reg.get("exists")) or bool(doc) or any(item.get("exists") for item in linked_regs),
                    "in_source_registry": in_registry,
                    "in_atomic_index": in_index,
                    "source_active": bool((reg and reg.get("active_versions", 0) >= 1) or any(item.get("active_versions", 0) >= 1 for item in linked_regs)),
                    "source_version": (reg or (linked_regs[0] if linked_regs else {})).get("version_count"),
                    "index_status": (reg or (linked_regs[0] if linked_regs else {})).get("index_status"),
                    "evidence_count": (doc or {}).get("evidence_count", 0),
                    "body_evidence_count": (doc or {}).get("body_evidence_count", 0),
                    "body_chars": (doc or {}).get("body_chars", 0),
                    "linked_targets": targets,
                    "linked_source_status": [{key: item.get(key) for key in ("source_id", "source_path", "body_status", "index_status", "exists")} for item in linked_regs],
                    "codes": codes,
                }
            )

    usable = sum(1 for r in rows if r["codes"] == ["OK"])
    total = len(rows)
    per_question_ok = sum(
        1
        for qid in {r["question_id"] for r in rows}
        if all(r["codes"] == ["OK"] for r in rows if r["question_id"] == qid)
    )
    question_total = len({r["question_id"] for r in rows})

    result = {
        "task": "T01_SOURCE_COVERAGE_AUDIT",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "gold_question_file": str(GOLD_PATH),
        "question_count": question_total,
        "expected_source_refs": total,
        "registered_source_count": len(sources),
        "indexed_document_count": len(docs),
        "source_coverage_rate": round(usable / total, 4) if total else None,
        "question_coverage_rate": round(per_question_ok / question_total, 4) if question_total else None,
        "error_code_distribution": dict(code_counter.most_common()),
        "registry_only_documents": sorted(
            [k for k in registered_by_name if k not in docs]
        )[:50],
        "index_only_documents_count": sum(1 for k in docs if k not in registered_by_name),
        "rows": rows,
    }

    (OUT / "source_coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n[T01] Source Coverage 审计结果")
    print(f"  问题数量            : {question_total}")
    print(f"  期望来源引用数      : {total}")
    print(f"  Source Coverage Rate: {result['source_coverage_rate']:.2%}")
    print(f"  问题级覆盖率        : {result['question_coverage_rate']:.2%}")
    print(f"  已登记 Source       : {len(sources)}")
    print(f"  已索引 Document     : {len(docs)}")
    print(f"  错误码分布          : {result['error_code_distribution']}")
    print(f"  输出目录            : {OUT}")
    return 0


def _body_fragment_chars(text: str) -> int:
    if not text.strip() or text.lstrip().startswith("#"):
        return 0
    body = re.sub(r"\[\[[^\]]+\]\]|\[[^\]]+\]\(file:///[^)]+\)|file://\S+|https?://\S+", "", text)
    compact = re.sub(r"[\s`*_#|]+", "", body)
    if len(compact) < 8 or re.fullmatch(r"[\d.、，：:;；()（）\-—]+", compact):
        return 0
    if compact in {"表格：", "关联内容", "相关来源", "相关概念"}:
        return 0
    return len(compact)


if __name__ == "__main__":
    raise SystemExit(main())
