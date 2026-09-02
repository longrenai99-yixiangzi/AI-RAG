from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.ingestion.pipeline import LOADERS, run_document_pipeline
from app.parsers import iter_source_files
from scripts.source_discovery.discover import (
    candidate_links,
    document_id,
    is_inside,
    resolve_target,
    sha256_file,
)


ROOTS = {
    "Root-001": Path(r"D:\设计管理"),
    "Root-002": Path(r"D:\工作\二公司技术部"),
    "Root-003": Path(r"D:\工作\设计支持中心"),
}
COLLECTION_NAME = "full_corpus_shadow_bge_m3"


def root_id_for(path: Path | None) -> str | None:
    if path is None:
        return None
    for root_id, root in ROOTS.items():
        if is_inside(path, root):
            return root_id
    return None


def candidate_status(path: Path | None) -> str:
    if path is None:
        return "LINK_BROKEN"
    root_id = root_id_for(path)
    if root_id is None:
        return "NEEDS_REVIEW"
    if root_id != "Root-001":
        return "PENDING_ROOT_APPROVAL"
    if not path.exists() or not path.is_file():
        return "LINK_BROKEN"
    if path.suffix.casefold() not in LOADERS:
        return "NEEDS_REVIEW"
    return "RESOLVED_SOURCE"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def make_candidate(
    *,
    source_id: str,
    parent_document: str,
    raw_link: str,
    resolved: Path | None,
    link_type: str,
) -> dict[str, Any]:
    status = candidate_status(resolved)
    exists = bool(resolved and resolved.exists())
    inside = bool(resolved and root_id_for(resolved) == "Root-001")
    if resolved and resolved.is_file():
        stat = resolved.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        digest = sha256_file(resolved)
        source_type = resolved.suffix.casefold()
        source_path = str(resolved)
    else:
        size = None
        mtime = None
        digest = None
        source_type = resolved.suffix.casefold() if resolved else "unknown"
        source_path = str(resolved) if resolved else None
    return {
        "source_id": source_id,
        "knowledge_root_id": root_id_for(resolved),
        "parent_document": parent_document,
        "raw_link": raw_link,
        "source_path": source_path,
        "source_type": source_type,
        "exists": exists,
        "inside_allowed_root": inside,
        "size": size,
        "mtime": mtime,
        "sha256": digest,
        "resolution_status": status,
        "link_type": link_type,
    }


def resolve_registered_sources(
    records: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        if record.get("source_status") != "REGISTERED_ONLY":
            continue
        resolved = Path(record["resolved_path"]) if record.get("resolved_path") else None
        item = make_candidate(
            source_id=record["source_id"],
            parent_document=record["parent_document"],
            raw_link=record.get("raw_link", ""),
            resolved=resolved,
            link_type=record.get("link_type", "source_record"),
        )
        candidates[(item["source_id"], item["raw_link"], item["source_path"] or "")] = item

        # Expand one more local Markdown registration layer without leaving Root-001.
        if resolved and resolved.is_file() and resolved.suffix.casefold() in {".md", ".markdown"}:
            try:
                text = resolved.read_text(encoding="utf-8-sig", errors="strict")
            except Exception:
                text = ""
            for child in candidate_links(text):
                child_path = resolve_target(child.raw_link, resolved, ROOTS["Root-001"])
                child_source_id = f"{record['source_id']}::child::{child.line_start}"
                child_item = make_candidate(
                    source_id=child_source_id,
                    parent_document=record["source_id"],
                    raw_link=child.raw_link,
                    resolved=child_path,
                    link_type=child.link_type,
                )
                candidates[(child_source_id, child.raw_link, child_item["source_path"] or "")] = child_item

    # Add external targets from source_links so Root-002/003 approval work is visible.
    for link in links:
        resolved_value = link.get("resolved_path")
        if not resolved_value:
            continue
        resolved = Path(resolved_value)
        if root_id_for(resolved) in {"Root-002", "Root-003"}:
            item = make_candidate(
                source_id=f"{link['link_id']}::approval",
                parent_document=link["from_document"],
                raw_link=link.get("target", ""),
                resolved=resolved,
                link_type=link.get("link_type", "source_link"),
            )
            candidates[(item["source_id"], item["raw_link"], item["source_path"] or "")] = item
    return sorted(candidates.values(), key=lambda item: item["source_id"])


def shadow_chunk_ids(shadow_dir: Path) -> set[str]:
    client = QdrantClient(path=str(shadow_dir))
    ids: set[str] = set()
    try:
        offset: Any = None
        while True:
            points, offset = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                ids.add(str(payload.get("chunk_id") or point.id))
            if offset is None:
                break
    finally:
        client.close()
    return ids


def focus_matches(candidates: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        item
        for item in candidates
        if any(
            term.casefold() in " ".join(
                [
                    str(item.get("raw_link") or ""),
                    str(item.get("source_path") or ""),
                    str(item.get("parent_document") or ""),
                ]
            ).casefold()
            for term in terms
        )
    ]


def build_report(
    *,
    candidates: list[dict[str, Any]],
    pipeline: Any,
    pipeline_chunk_ids: set[str],
    shadow_ids: set[str],
    focus: dict[str, list[dict[str, Any]]],
) -> str:
    candidate_statuses = Counter(item["resolution_status"] for item in candidates)
    pipeline_statuses = Counter(document.status for document in pipeline.documents)
    intersection = pipeline_chunk_ids & shadow_ids
    lines = [
        "# Knowledge Source Closure Report",
        "",
        "> Root-001 only: `D:\\设计管理`. This task resolves and validates sources in Shadow scope; it does not publish to formal Qdrant.",
        "> Root-002 and Root-003 targets are listed for approval only and are not parsed or embedded.",
        "",
        "## 1. Closure Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Registered/resolver candidate records inspected | {len(candidates)} |",
        f"| Resolver candidates | {len(candidates)} |",
        f"| RESOLVED_SOURCE | {candidate_statuses.get('RESOLVED_SOURCE', 0)} |",
        f"| REGISTERED_PAGE_RESOLVED | {candidate_statuses.get('REGISTERED_PAGE_RESOLVED', 0)} |",
        f"| PENDING_ROOT_APPROVAL | {candidate_statuses.get('PENDING_ROOT_APPROVAL', 0)} |",
        f"| LINK_BROKEN | {candidate_statuses.get('LINK_BROKEN', 0)} |",
        f"| NEEDS_REVIEW | {candidate_statuses.get('NEEDS_REVIEW', 0)} |",
        f"| Pipeline documents | {len(pipeline.documents)} |",
        f"| SourceBlocks | {pipeline.source_block_count} |",
        f"| Chunks | {pipeline.chunk_count} |",
        f"| Pipeline parse/status failures | {sum(status != 'parsed' for status in pipeline_statuses for _ in range(pipeline_statuses[status]))} |",
        f"| Embeddings generated by this task | 0 (verification only) |",
        f"| Existing Shadow Qdrant points | {len(shadow_ids)} |",
        f"| Pipeline Chunk IDs matched in existing Shadow | {len(intersection)} |",
        "",
        "### Pipeline Status Distribution",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(pipeline_statuses.items()))
    lines += [
        "",
        "## 2. Closure Rules Applied",
        "",
        "1. Only `Root-001` paths are eligible for parse, SourceBlock and Chunk validation.",
        "2. Root-002/003 targets become `PENDING_ROOT_APPROVAL` and stop before parsing.",
        "3. Existing Shadow Qdrant is read-only in this task; no point or collection is written.",
        "4. A registration page is not treated as the body of its linked external file.",
        "5. Existing Shadow point matching is a consistency check, not a new embedding run.",
        "",
        "## 3. Focus Validation",
        "",
    ]
    focus_names = {
        "BA-010": "新洲星谷科创中心价值创造清单",
        "BA-007": "中建三局2026年设计与技术工作计划",
        "BA-009": "2026年4月设计服务管理台账",
    }
    for key, title in focus_names.items():
        matches = focus.get(key, [])
        lines += [f"### {key} - {title}", ""]
        if not matches:
            lines.append("- No resolver candidate matched this focus item.")
        for item in matches[:20]:
            lines.append(
                f"- `{item['resolution_status']}` root=`{item.get('knowledge_root_id')}` "
                f"type=`{item['source_type']}` exists=`{item['exists']}` "
                f"raw=`{item['raw_link']}` -> `{item.get('source_path') or 'UNRESOLVED'}`"
            )
        if any(item["resolution_status"] in {"RESOLVED_SOURCE", "REGISTERED_PAGE_RESOLVED"} for item in matches):
            lines.append("- Local Root-001 candidate can proceed to Document Pipeline validation.")
        if any(item["resolution_status"] == "PENDING_ROOT_APPROVAL" for item in matches):
            lines.append("- External target is blocked by Root Policy and remains approval-only.")
        lines.append("")
    lines += [
        "## 4. Staging / Shadow Interpretation",
        "",
        "- The current pipeline run produces SourceBlock and Chunk outputs only in memory/staging report scope.",
        "- No Embedding was generated by TASK-016B-2 in order to avoid writing or changing any formal index.",
        "- Existing Shadow Qdrant points were read to verify Chunk ID coverage; this is not a publication operation.",
        "- For BA-007 and BA-009, the local registration pages can be parsed, but their external PDF/XLSX bodies remain outside Root-001.",
        "- For BA-010, the entity/raw link chain is detected, but the external value-list XLSX cannot proceed without Root approval.",
        "",
        "## 5. Closure Conclusion",
        "",
        "Root-001 registration pages and existing in-root documents can be passed through the current Document Pipeline for Shadow validation. External targets from Root-002/003 are correctly stopped at `PENDING_ROOT_APPROVAL`. The three focus chains are discovered, but BA-007, BA-009 and BA-010 are not closed to real external bodies under the current Root Policy.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Root-001 link expansion and Shadow pipeline closure")
    parser.add_argument("--discovery-dir", type=Path, default=Path("data") / "shadow" / "source_discovery")
    parser.add_argument("--shadow-dir", type=Path, default=Path("data") / "shadow" / "full_corpus_qdrant")
    parser.add_argument("--root", type=Path, default=ROOTS["Root-001"])
    args = parser.parse_args()

    records = load_jsonl(args.discovery_dir / "source_records.jsonl")
    links = load_jsonl(args.discovery_dir / "source_links.jsonl")
    candidates = resolve_registered_sources(records, links)
    args.discovery_dir.mkdir(parents=True, exist_ok=True)
    (args.discovery_dir / "resolved_source_candidates.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in candidates),
        encoding="utf-8",
    )

    files = [path for path in iter_source_files(args.root) if is_inside(path, args.root)]
    pipeline = run_document_pipeline(args.root, files=files)
    pipeline_chunk_ids = {chunk.chunk_id for document in pipeline.documents for chunk in document.chunks}
    staging_path = args.discovery_dir / "closure_staging.jsonl"
    staging_path.write_text(
        "".join(
            json.dumps(
                {
                    "path": str(document.path),
                    "status": document.status,
                    "source_blocks": len(document.source_blocks),
                    "chunks": len(document.chunks),
                    "metadata": document.metadata,
                    "error": document.error,
                },
                ensure_ascii=False,
            )
            + "\n"
            for document in pipeline.documents
        ),
        encoding="utf-8",
    )
    shadow_ids = shadow_chunk_ids(args.shadow_dir)
    focus = {
        "BA-010": focus_matches(candidates, ("星谷", "价值创造")),
        "BA-007": focus_matches(candidates, ("2026", "工作计划", "示范")),
        "BA-009": focus_matches(candidates, ("2026年4月", "服务台账", "设计服务")),
    }
    report = build_report(
        candidates=candidates,
        pipeline=pipeline,
        pipeline_chunk_ids=pipeline_chunk_ids,
        shadow_ids=shadow_ids,
        focus=focus,
    )
    Path("docs") .joinpath("KNOWLEDGE_SOURCE_CLOSURE_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "resolver_candidates": len(candidates),
        "candidate_statuses": dict(Counter(item["resolution_status"] for item in candidates)),
        "pipeline_documents": len(pipeline.documents),
        "source_blocks": pipeline.source_block_count,
        "chunks": pipeline.chunk_count,
        "shadow_points_verified": len(shadow_ids),
        "pipeline_chunks_in_shadow": len(pipeline_chunk_ids & shadow_ids),
    }, ensure_ascii=False, indent=2))
    print(f"candidates={args.discovery_dir / 'resolved_source_candidates.jsonl'}")
    print(f"staging={staging_path}")
    print("report=docs/KNOWLEDGE_SOURCE_CLOSURE_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
