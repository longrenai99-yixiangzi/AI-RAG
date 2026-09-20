"""T03 - Metadata 与知识结构审计（只读）。

审计每条 Atomic Evidence 的机器结构完备度，区分：
    强事实 Metadata（只能由来源明确得到，可用于硬过滤）
    推断 Metadata（允许模型推断，但只能作为排序提示）

输出：
    evaluation/knowledge_os_system_audit/t03/
        metadata_audit.json         字段填充率 / 置信度 / 复核状态
        knowledge_structure.json    人类知识结构 vs 机器知识结构
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t03"
ATOMIC_PATH = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
STATE_PATH = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
HIERARCHICAL = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"

# 强事实：只能由来源明确得到，可作为硬过滤依据
STRONG_FIELDS = {
    "year": ("year",),
    "project": ("project", "project_name"),
    "organization": ("organization", "org"),
    "professional": ("discipline", "professional"),
    "source_version": ("sha256",),
    "effective_status": ("effective_status",),
    "document_type": ("file_type",),
    "document_title": ("file_name",),
    "section": ("heading_path",),
    "page": (("location", "page"), ("location", "slide"), ("location", "sheet"), ("location", "line_start")),
}

# 推断：允许模型推断，只能作为排序/软提示
INFERRED_FIELDS = {
    "business_topic": ("business_topic",),
    "knowledge_domain": ("board",),
    "knowledge_node": ("knowledge_node",),
    "knowledge_type": ("knowledge_type",),
    "document_role": ("document_role",),
    "authority_level": ("authority_level",),
    "usage_scene": ("usage_scene",),
}


def get_path(rec: dict, meta: dict, path) -> object:
    """按候选路径取值，支持顶层字段、metadata 字段与嵌套元组路径。"""
    for key in path:
        if isinstance(key, tuple):
            cur = rec.get("location") or {}
            val = cur.get(key[1]) if len(key) > 1 else None
            if val not in (None, "", []):
                return val
        else:
            for src in (rec, meta):
                if isinstance(src, dict) and key in src:
                    val = src.get(key)
                    if val not in (None, "", []):
                        return val
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    total = 0
    filled: dict[str, int] = defaultdict(int)
    field_present: dict[str, int] = defaultdict(int)
    confidence_sum: dict[str, float] = defaultdict(float)
    confidence_cnt: dict[str, int] = defaultdict(int)
    review_status = Counter()
    metadata_rule = Counter()
    by_type_fill: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    by_type_total: Counter = Counter()
    all_metadata_keys: Counter = Counter()

    # 来源归属（机器结构）
    doc_to_source: dict[str, str] = {}
    source_docs: dict[str, set] = defaultdict(set)

    with ATOMIC_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            meta = rec.get("metadata") or {}
            ftype = rec.get("file_type") or "<none>"
            by_type_total[ftype] += 1
            for k in meta:
                all_metadata_keys[k] += 1

            for name, paths in {**STRONG_FIELDS, **INFERRED_FIELDS}.items():
                val = get_path(rec, meta, paths)
                if val not in (None, "", []):
                    filled[name] += 1
                    by_type_fill[ftype][name] += 1

            conf = meta.get("metadata_confidence") or {}
            if isinstance(conf, dict):
                for k, v in conf.items():
                    if isinstance(v, (int, float)):
                        confidence_sum[k] += v
                        confidence_cnt[k] += 1
            review_status[meta.get("metadata_review_status") or "<none>"] += 1
            rule = meta.get("metadata_rule") or {}
            if isinstance(rule, dict):
                for k, v in rule.items():
                    metadata_rule[f"{k}={v}"] += 1

            did = rec.get("document_id")
            spath = rec.get("source_path") or ""
            if did:
                doc_to_source[did] = spath
                source_docs[spath].add(did)

    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    # 人类知识结构（前端知识框架）
    knowledge_nodes = state.get("knowledge", {})
    human_structure = {
        "knowledge_item_count": len(knowledge_nodes),
        "node_ids": sorted({k.get("node_id") for k in knowledge_nodes.values() if k.get("node_id")}),
        "status_distribution": dict(Counter(k.get("status") for k in knowledge_nodes.values())),
        "question_variant_count": len(state.get("question_variants", {})),
    }

    field_report = {}
    for group, fields, kind in (
        ("strong", STRONG_FIELDS, "strong_fact"),
        ("inferred", INFERRED_FIELDS, "inferred"),
    ):
        for name in fields:
            field_report[name] = {
                "group": group,
                "kind": kind,
                "fill_count": filled.get(name, 0),
                "fill_rate": round(filled.get(name, 0) / total, 4) if total else 0,
                "missing_count": total - filled.get(name, 0),
                "avg_confidence": round(confidence_sum[name] / confidence_cnt[name], 3)
                if confidence_cnt.get(name)
                else None,
            }

    strong_rates = [v["fill_rate"] for v in field_report.values() if v["group"] == "strong"]
    inferred_rates = [v["fill_rate"] for v in field_report.values() if v["group"] == "inferred"]

    result = {
        "task": "T03_METADATA_AUDIT",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "total_records": total,
        "fields": field_report,
        "strong_fact_avg_fill_rate": round(sum(strong_rates) / len(strong_rates), 4) if strong_rates else 0,
        "inferred_avg_fill_rate": round(sum(inferred_rates) / len(inferred_rates), 4) if inferred_rates else 0,
        "metadata_review_status_distribution": dict(review_status.most_common()),
        "metadata_rule_distribution": dict(metadata_rule.most_common(20)),
        "metadata_key_coverage": {
            k: round(v / total, 4) for k, v in all_metadata_keys.most_common()
        },
        "fill_rate_by_file_type": {
            k: {
                "total": by_type_total[k],
                **{f: round(by_type_fill[k].get(f, 0) / by_type_total[k], 4) for f in field_report},
            }
            for k in sorted(by_type_total, key=lambda x: -by_type_total[x])
        },
        "machine_structure": {
            "source_count": len(state.get("sources", {})),
            "document_count": len(doc_to_source),
            "atomic_evidence_count": total,
            "documents_per_source": {
                k: len(v) for k, v in sorted(source_docs.items(), key=lambda x: -len(x[1]))[:20]
            },
            "source_version_tracked": bool(state.get("sources")),
            "entity_field_present": all_metadata_keys.get("entity", 0),
            "relation_field_present": all_metadata_keys.get("relation", 0),
            "table_field_present": all_metadata_keys.get("table", 0),
            "parent_chunk_field_present": all_metadata_keys.get("parent_chunk_id", 0),
            "child_chunk_field_present": all_metadata_keys.get("child_chunk_ids", 0),
        },
        "human_structure": human_structure,
        "layer_audit": {
            "raw_atomic": _layer_audit(ATOMIC_PATH, "raw_atomic"),
            "documents": _layer_audit(HIERARCHICAL / "document_index" / "records.jsonl", "document"),
            "sections": _layer_audit(HIERARCHICAL / "section_index" / "records.jsonl", "section"),
            "tables": _layer_audit(HIERARCHICAL / "table_index" / "records.jsonl", "table"),
            "frozen_atomic": _layer_audit(HIERARCHICAL / "atomic_evidence.jsonl", "frozen_atomic"),
        },
    }

    (OUT / "metadata_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n[T03] Metadata 审计结果")
    print(f"  记录总数 : {total}")
    print(f"  强事实平均填充率 : {result['strong_fact_avg_fill_rate']:.2%}")
    print(f"  推断字段平均填充率: {result['inferred_avg_fill_rate']:.2%}")
    print("  字段明细 :")
    for name, v in sorted(field_report.items(), key=lambda x: x[1]["fill_rate"]):
        print(
            f"      {name:<18} [{v['group']:<8}] fill={v['fill_rate']:>7.2%}  conf={v['avg_confidence']}"
        )
    print(f"  review 状态 : {result['metadata_review_status_distribution']}")
    print(f"  输出目录    : {OUT}")
    return 0


def _layer_audit(path: Path, layer: str) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    fields = ("organization", "project", "year", "specialty")
    filled = Counter()
    suspicious_projects = []
    for row in rows:
        scope = row.get("scope") or {}
        metadata = row.get("metadata") or {}
        for field in fields:
            value = row.get(field) or scope.get(field) or metadata.get(field)
            if value not in (None, "", []):
                filled[field] += 1
        projects = row.get("project") or scope.get("project") or metadata.get("project") or []
        projects = projects if isinstance(projects, list) else [projects]
        for project in projects:
            text = str(project)
            if len(text) > 30 or any(marker in text for marker in ("什么", "哪些", "如何", "多少", "必须", "建议", "表达", "问题", "内容")):
                if len(suspicious_projects) < 30:
                    suspicious_projects.append({"record_id": row.get("document_id") or row.get("section_id") or row.get("evidence_id"), "value": text})
    total = len(rows)
    return {
        "layer": layer, "path": str(path), "records": total,
        "scope_fill_rate": {field: round(filled[field] / total, 4) if total else None for field in fields},
        "document_type_rate": round(sum(bool(row.get("document_type") or (row.get("metadata") or {}).get("file_type") or row.get("file_type")) for row in rows) / total, 4) if total else None,
        "heading_rate": round(sum(bool(row.get("heading_path")) for row in rows) / total, 4) if total else None,
        "location_rate": round(sum(bool(row.get("location") or row.get("source_location")) for row in rows) / total, 4) if total else None,
        "source_version_rate": round(sum(bool(row.get("source_version") or row.get("sha256") or (row.get("metadata") or {}).get("sha256")) for row in rows) / total, 4) if total else None,
        "parent_relation_rate": round(sum(bool(row.get("parent_evidence_id") or row.get("parent_heading_path") or row.get("parent_heading")) for row in rows) / total, 4) if total else None,
        "suspicious_project_values": suspicious_projects,
        "suspicious_project_count_sampled": len(suspicious_projects),
    }


if __name__ == "__main__":
    raise SystemExit(main())
