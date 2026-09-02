from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - project already carries PyYAML
    yaml = None


SUPPORTED_FILE_TYPES = {".pdf", ".docx", ".xlsx", ".pptx", ".md", ".markdown"}
DISCOVERY_ROOTS = {"wiki", "raw"}
FRONT_MATTER_KEYS = {
    "source",
    "sources",
    "raw",
    "attachments",
    "related_documents",
}
MARKDOWN_LINK_RE = re.compile(r"!??\[[^\]]*\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|#^]+)(?:#[^\]|^]*)?(?:\|[^\]]*)?\]\]")
WINDOWS_PATH_RE = re.compile(
    r"(?<![A-Za-z])(?P<path>[A-Za-z]:[\\/][^\s<>\"'\])}]+(?:\.[A-Za-z0-9]{1,8})?)"
)


@dataclass(slots=True)
class LinkCandidate:
    raw_link: str
    link_type: str
    line_start: int
    line_end: int
    column_start: int
    column_end: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def document_id(path: Path) -> str:
    value = str(path).replace("\\", "/").casefold()
    return "doc-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def source_id(parent: Path, raw_link: str, resolved: Path | None) -> str:
    value = "|".join(
        [
            str(parent).casefold(),
            raw_link,
            str(resolved).casefold() if resolved else "",
        ]
    )
    return "src-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def decode_file_uri(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.casefold() != "file":
        return value
    path = urllib.parse.unquote(parsed.path)
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return path


def clean_target(value: str) -> str:
    value = value.strip().strip("<>\"'")
    value = value.split("#", 1)[0].split("^", 1)[0].strip()
    return decode_file_uri(value)


def line_location(text: str, offset: int, length: int) -> tuple[int, int, int, int]:
    line_start = text.count("\n", 0, offset) + 1
    line_end = text.count("\n", 0, offset + length) + 1
    last_newline = text.rfind("\n", 0, offset)
    column_start = offset - last_newline
    column_end = column_start + length
    return line_start, line_end, column_start, column_end


def front_matter(text: str) -> tuple[dict[str, Any], int]:
    lines = text.splitlines()
    if not lines or lines[0].strip().lstrip("\ufeff") != "---":
        return {}, 0
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None or yaml is None:
        return {}, 0
    try:
        payload = yaml.safe_load("\n".join(lines[1:end])) or {}
    except Exception:
        return {"__parse_error__": "front matter parse failed"}, end
    return payload if isinstance(payload, dict) else {}, end


def nested_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from nested_values(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from nested_values(child)


def candidate_links(text: str) -> list[LinkCandidate]:
    candidates: list[LinkCandidate] = []
    seen: set[tuple[str, int, str]] = set()

    def add(raw: str, link_type: str, offset: int, length: int) -> None:
        raw = raw.strip()
        if not raw:
            return
        line_start, line_end, column_start, column_end = line_location(text, offset, length)
        key = (raw, line_start, link_type)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            LinkCandidate(
                raw_link=raw,
                link_type=link_type,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
            )
        )

    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).split(" ", 1)[0]
        add(target, "markdown_link", match.start(1), len(target))
    for match in WIKILINK_RE.finditer(text):
        add(match.group(1), "obsidian_wikilink", match.start(1), len(match.group(1)))
    for match in WINDOWS_PATH_RE.finditer(text):
        add(match.group("path"), "windows_absolute_path", match.start("path"), len(match.group("path")))

    payload, front_end = front_matter(text)
    if payload.get("__parse_error__"):
        add("<front_matter_parse_error>", "front_matter", 0, 3)
    for key in FRONT_MATTER_KEYS:
        if key not in payload:
            continue
        for value in nested_values(payload[key]):
            if any(token in value for token in ("/", "\\", ".pdf", ".docx", ".xlsx", ".pptx", ".md", "file://")):
                offset = text.find(value)
                add(value, "front_matter", max(offset, 0), len(value))

    return candidates


def resolve_target(raw_link: str, parent: Path, root: Path) -> Path | None:
    target = clean_target(raw_link)
    if target.startswith("<") or target.startswith("http://") or target.startswith("https://"):
        return None
    path = Path(target)
    if path.is_absolute():
        return path
    normalized = target.replace("/", "\\")
    if normalized.casefold().startswith(("wiki\\", "raw\\", "concepts\\", "entities\\", "queries\\")):
        path = root.joinpath(*normalized.split("\\"))
    else:
        path = parent.parent.joinpath(*normalized.split("\\"))
    if path.exists():
        return path
    if path.suffix == "":
        for suffix in (".md", ".markdown", ".pdf", ".docx", ".xlsx", ".pptx"):
            candidate = path.with_suffix(suffix)
            if candidate.exists():
                return candidate
    return path


def status_for(resolved: Path | None, root: Path) -> tuple[str, bool | None]:
    if resolved is None:
        return "NEEDS_REVIEW", None
    inside = is_inside(resolved, root)
    if not resolved.exists():
        return "LINK_BROKEN", inside
    if not inside:
        return "NEEDS_REVIEW", inside
    if resolved.is_dir():
        return "NEEDS_REVIEW", inside
    if resolved.suffix.casefold() in {".md", ".markdown"} and is_registration_only(resolved):
        return "REGISTERED_ONLY", inside
    return "BODY_AVAILABLE", inside


def is_registration_only(path: Path) -> bool:
    """Detect a Markdown page whose usable content is only a source registration/link."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="strict")
    except Exception:
        return False
    if not any(token in text.casefold() for token in ("file://", ".pdf", ".docx", ".xlsx", ".pptx")):
        return False
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
        if end is not None:
            lines = lines[end + 1 :]
    body = "\n".join(lines)
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    body = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[\[[^\]]*\]\]", "", body)
    body = re.sub(r"file://\S+", "", body)
    body = re.sub(r"(?im)^\s*(source|sources|来源|关联内容|related_documents)\s*[:：]?.*$", "", body)
    meaningful = re.sub(r"[\s\-*_`>|\[\](){}:：]", "", body)
    return len(meaningful) < 120


def discover(root: Path, output_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    root = root.resolve()
    markdown_files = [
        path
        for path in root.rglob("*.md")
        if any(part.casefold() in DISCOVERY_ROOTS for part in path.relative_to(root).parts)
    ]
    markdown_files += [
        path
        for path in root.rglob("*.markdown")
        if any(part.casefold() in DISCOVERY_ROOTS for part in path.relative_to(root).parts)
    ]
    markdown_files = sorted(set(markdown_files))
    records: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for parent in markdown_files:
        text = parent.read_text(encoding="utf-8-sig", errors="strict")
        parent_id = document_id(parent)
        for candidate in candidate_links(text):
            resolved = resolve_target(candidate.raw_link, parent, root)
            status, inside = status_for(resolved, root)
            resolved_path = str(resolved.resolve(strict=False)) if resolved else None
            link_id = "link-" + hashlib.sha256(
                f"{parent_id}|{candidate.raw_link}|{candidate.line_start}".encode("utf-8")
            ).hexdigest()[:24]
            resolution_status = "RESOLVED" if resolved and resolved.exists() else "MISSING"
            if resolved is None:
                resolution_status = "UNRESOLVED"
            links.append(
                {
                    "link_id": link_id,
                    "from_document": parent_id,
                    "from_path": str(parent),
                    "target": candidate.raw_link,
                    "link_type": candidate.link_type,
                    "line_location": {
                        "line_start": candidate.line_start,
                        "line_end": candidate.line_end,
                        "column_start": candidate.column_start,
                        "column_end": candidate.column_end,
                    },
                    "resolved_path": resolved_path,
                    "resolution_status": resolution_status,
                }
            )
            if resolved and resolved.is_file():
                stat = resolved.stat()
                file_type = resolved.suffix.casefold() or "unknown"
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
                digest = sha256_file(resolved)
            else:
                file_type = resolved.suffix.casefold() if resolved else "unknown"
                size = None
                mtime = None
                digest = None
            sid = source_id(parent, candidate.raw_link, resolved)
            records[sid] = {
                "source_id": sid,
                "parent_document": parent_id,
                "parent_path": str(parent),
                "raw_link": candidate.raw_link,
                "resolved_path": resolved_path,
                "file_type": file_type,
                "exists": bool(resolved and resolved.exists()),
                "inside_allowed_root": inside,
                "size": size,
                "mtime": mtime,
                "sha256": digest,
                "source_status": status,
                "link_type": candidate.link_type,
                "line_location": {
                    "line_start": candidate.line_start,
                    "line_end": candidate.line_end,
                },
            }

    source_records = sorted(records.values(), key=lambda item: item["source_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_records.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in source_records),
        encoding="utf-8",
    )
    (output_dir / "source_links.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in links),
        encoding="utf-8",
    )
    report = build_report(root, markdown_files, source_records, links)
    (Path("docs") / "SOURCE_DISCOVERY_REPORT.md").write_text(report, encoding="utf-8")
    return source_records, links, {
        "markdown_pages": len(markdown_files),
        "source_records": len(source_records),
        "source_links": len(links),
    }


def build_report(root: Path, markdown_files: list[Path], records: list[dict[str, Any]], links: list[dict[str, Any]]) -> str:
    type_counts = Counter(item["file_type"] for item in records)
    unique_type_counts = Counter(
        (item["file_type"], str(item["resolved_path"]).casefold())
        for item in records
        if item["exists"] and item["resolved_path"]
    )
    unique_by_type = Counter(file_type for file_type, _ in unique_type_counts)
    status_counts = Counter(item["source_status"] for item in records)
    existing = sum(item["exists"] is True for item in records)
    missing = sum(item["source_status"] == "LINK_BROKEN" for item in records)
    top_registered = [item for item in records if item["source_status"] == "REGISTERED_ONLY"][:50]
    focus_terms = {
        "BA-003": ("厂房", "方案比选"),
        "BA-006": ("2026", "设计与技术工作计划"),
        "BA-007": ("示范项目", "2026"),
        "BA-009": ("2026年4月", "服务"),
        "BA-010": ("星谷", "价值创造"),
    }
    lines = [
        "# Source Discovery Report",
        "",
        f"> Root: `{root}`. Read-only discovery only; no formal Qdrant write and no automatic publication.",
        "",
        "## 1. Discovery Summary",
        "",
        f"- Markdown registration/discovery pages: `{len(markdown_files)}`",
        f"- Discovered external/local links: `{len(links)}`",
        f"- SourceRecord count: `{len(records)}`",
        f"- Existing resolved files: `{existing}`",
        f"- Missing resolved files: `{missing}`",
        f"- PDF SourceRecord records: `{type_counts.get('.pdf', 0)}`; unique existing files: `{unique_by_type.get('.pdf', 0)}`",
        f"- DOCX SourceRecord records: `{type_counts.get('.docx', 0)}`; unique existing files: `{unique_by_type.get('.docx', 0)}`",
        f"- XLSX SourceRecord records: `{type_counts.get('.xlsx', 0)}`; unique existing files: `{unique_by_type.get('.xlsx', 0)}`",
        f"- PPTX SourceRecord records: `{type_counts.get('.pptx', 0)}`; unique existing files: `{unique_by_type.get('.pptx', 0)}`",
        f"- Markdown SourceRecord records: `{type_counts.get('.md', 0) + type_counts.get('.markdown', 0)}`; unique existing files: `{unique_by_type.get('.md', 0) + unique_by_type.get('.markdown', 0)}`",
        "",
        "### Source Status Distribution",
        "",
        "| source_status | count |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(status_counts.items()))
    lines += [
        "",
        "## 2. Top 50 REGISTERED_ONLY",
        "",
        "| source_id | parent_path | raw_link | resolved_path | type | exists | inside_allowed_root |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in top_registered:
        lines.append(
            f"| {item['source_id']} | {item['parent_path']} | {item['raw_link']} | "
            f"{item['resolved_path'] or '-'} | {item['file_type']} | {item['exists']} | {item['inside_allowed_root']} |"
        )
    if not top_registered:
        lines.append("| - | - | - | - | - | - | - |")
    lines += ["", "## 3. Focus Validation", ""]
    for label, terms in focus_terms.items():
        matches = [
            item
            for item in records
            if any(term.casefold() in (item.get("raw_link") or "").casefold() for term in terms)
            or any(term.casefold() in (item.get("resolved_path") or "").casefold() for term in terms)
            or any(term.casefold() in (item.get("parent_path") or "").casefold() for term in terms)
        ]
        lines += [f"### {label}", "", f"Discovery records matched: `{len(matches)}`", ""]
        for item in matches[:20]:
            lines.append(
                f"- `{item['source_status']}` `{item['file_type']}` `{item['raw_link']}` -> "
                f"`{item['resolved_path'] or 'UNRESOLVED'}`; parent=`{item['parent_path']}`"
            )
        if not matches:
            lines.append("- No matching discovery record.")
        lines.append("")
    lines += [
        "## 4. Status Semantics",
        "",
        "- `REGISTERED_ONLY`: a registration/link was found, but no usable local body was resolved.",
        "- `BODY_AVAILABLE`: a regular file exists inside the allowed root; it is not yet parsed or indexed by this discovery task.",
        "- `LINK_BROKEN`: a local-looking target was resolved but the target file does not exist.",
        "- `NEEDS_REVIEW`: the target is outside the allowed root, unresolved, a directory, or otherwise requires approval.",
        "",
        "## 5. Boundary and Next Step",
        "",
        "This task only creates SourceRecord and SourceLink discovery artifacts. It does not parse, chunk, embed, publish, or alter Qdrant.",
        "The next task may use these records to approve selected sources, load their bodies, and continue through staging with rollback.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only external source discovery")
    parser.add_argument("--root", type=Path, default=Path(r"D:\设计管理"))
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "shadow" / "source_discovery")
    args = parser.parse_args()
    records, links, counts = discover(args.root, args.output_dir)
    print(json.dumps({**counts, "status_counts": dict(Counter(item["source_status"] for item in records))}, ensure_ascii=False, indent=2))
    print(f"source_records={args.output_dir / 'source_records.jsonl'}")
    print(f"source_links={args.output_dir / 'source_links.jsonl'}")
    print(f"report={Path('docs') / 'SOURCE_DISCOVERY_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
