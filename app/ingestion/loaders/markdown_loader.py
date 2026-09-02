from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.domain import SourceBlock
from app.ingestion.normalization.markdown_normalizer import (
    normalize_markdown_block,
    normalize_markdown_text,
)


SUPPORTED_EXTENSIONS = {".md", ".markdown"}
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")


@dataclass(slots=True)
class MarkdownLoadResult:
    """Parser result; content is emitted only as standard SourceBlock objects."""

    status: str
    blocks: list[SourceBlock] = field(default_factory=list)
    front_matter: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class MarkdownLoader:
    """Strict UTF-8 Markdown loader kept separate from the active indexer."""

    def load(self, path: Path, document_id: str) -> MarkdownLoadResult:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return MarkdownLoadResult(status="unsupported_extension")

        try:
            text = normalize_markdown_text(path.read_bytes().decode("utf-8-sig"))
        except UnicodeDecodeError as error:
            return MarkdownLoadResult(
                status="encoding_error",
                error=f"UnicodeDecodeError: invalid UTF-8 at byte {error.start}",
            )
        except OSError as error:
            return MarkdownLoadResult(
                status="read_error",
                error=f"{type(error).__name__}: {error}",
            )

        if not text.strip():
            return MarkdownLoadResult(status="empty")

        lines = text.splitlines()
        body_start, front_matter, front_matter_error = self._parse_front_matter(lines)
        if front_matter_error:
            return MarkdownLoadResult(
                status="front_matter_error",
                front_matter=front_matter,
                error=front_matter_error,
            )
        if body_start >= len(lines):
            return MarkdownLoadResult(status="empty", front_matter=front_matter)

        blocks = self._build_blocks(
            path=path,
            document_id=document_id,
            lines=lines[body_start:],
            source_line_offset=body_start,
        )
        return MarkdownLoadResult(
            status="parsed" if blocks else "empty",
            blocks=blocks,
            front_matter=front_matter,
        )

    @staticmethod
    def _parse_front_matter(
        lines: list[str],
    ) -> tuple[int, dict[str, Any], str | None]:
        if not lines or lines[0].strip() != "---":
            return 0, {}, None

        closing_index: int | None = None
        for index in range(1, len(lines)):
            if lines[index].strip() in {"---", "..."}:
                closing_index = index
                break
        if closing_index is None:
            return 0, {}, "front matter starts with '---' but has no closing marker"

        raw_front_matter = "\n".join(lines[1:closing_index])
        try:
            parsed = yaml.safe_load(raw_front_matter) or {}
        except yaml.YAMLError as error:
            return 0, {}, f"YAML front matter error: {error}"
        if not isinstance(parsed, dict):
            return 0, {}, "YAML front matter must be a mapping"
        return closing_index + 1, parsed, None

    @classmethod
    def _build_blocks(
        cls,
        path: Path,
        document_id: str,
        lines: list[str],
        source_line_offset: int,
    ) -> list[SourceBlock]:
        headings: list[str] = []
        section_heading_path = ""
        section: list[tuple[int, str]] = []
        blocks: list[SourceBlock] = []

        def flush() -> None:
            nonlocal section
            non_empty = [(line_number, line) for line_number, line in section if line.strip()]
            if not non_empty:
                section = []
                return
            blocks.append(
                SourceBlock(
                    document_id=document_id,
                    source_path=str(path),
                    file_name=path.name,
                    text=normalize_markdown_block("\n".join(line for _, line in section)),
                    heading_path=section_heading_path,
                    location={
                        "line_start": non_empty[0][0],
                        "line_end": non_empty[-1][0],
                    },
                )
            )
            section = []

        for relative_line_number, line in enumerate(lines, start=1):
            line_number = source_line_offset + relative_line_number
            match = _HEADING_RE.match(line)
            if match:
                flush()
                level = len(match.group(1))
                title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
                if not title:
                    section.append((line_number, line))
                    continue
                headings = headings[: level - 1] + [title]
                section_heading_path = " > ".join(headings)
            section.append((line_number, line))
        flush()
        return blocks


def load_markdown(path: Path, document_id: str) -> MarkdownLoadResult:
    """Convenience function for callers that do not need a loader instance."""

    return MarkdownLoader().load(path, document_id)
