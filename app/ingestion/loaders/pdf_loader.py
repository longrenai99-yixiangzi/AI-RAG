from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import pymupdf

from app.domain import SourceBlock
from app.ingestion.quality.pdf_quality import PDFQualityResult, assess_pdf


@dataclass(slots=True)
class PDFLoadResult:
    """Parser result; page content is emitted only as standard SourceBlock objects."""

    status: str
    blocks: list[SourceBlock] = field(default_factory=list)
    quality: PDFQualityResult | None = None
    error: str | None = None


class PDFLoader:
    """Read-only PyMuPDF loader kept separate from the active parser and indexer."""

    def load(self, path: Path, document_id: str) -> PDFLoadResult:
        if path.suffix.lower() != ".pdf":
            return PDFLoadResult(
                status="read_error",
                error=f"不支持的文件扩展名：{path.suffix or '无扩展名'}",
            )

        try:
            with pymupdf.open(path) as pdf:
                quality = assess_pdf(pdf)
                blocks = self._build_blocks(pdf, path, document_id)
        except OSError as error:
            return PDFLoadResult(
                status="read_error",
                error=f"{type(error).__name__}: {error}",
            )
        except Exception as error:  # Isolate malformed PDF and page-level parser failures.
            return PDFLoadResult(
                status="read_error",
                error=f"{type(error).__name__}: {error}",
            )

        return PDFLoadResult(status=quality.status, blocks=blocks, quality=quality)

    @staticmethod
    def _build_blocks(pdf: pymupdf.Document, path: Path, document_id: str) -> list[SourceBlock]:
        blocks: list[SourceBlock] = []
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            blocks.append(
                SourceBlock(
                    document_id=document_id,
                    source_path=str(path),
                    file_name=path.name,
                    text=text,
                    location={"page": page_number, "text_length": len(text)},
                )
            )
        return blocks


def load_pdf(path: Path, document_id: str) -> PDFLoadResult:
    """Convenience function for callers that do not need a loader instance."""

    return PDFLoader().load(path, document_id)


def extract_value_creation_summary(text: str) -> dict[str, tuple[int, int, int]]:
    """Extract the stage-count summary table from the value-creation PDF."""
    lines = [re.sub(r"\s+", "", line) for line in text.splitlines() if line.strip()]
    title = next((index for index, line in enumerate(lines) if "设计价值创造点" in line and "专业" in line and "阶段" in line and "数量" in line), None)
    if title is None:
        return {}
    header = next((index for index in range(title + 1, len(lines)) if lines[index] == "方案设计"), None)
    if header is None:
        return {}
    start = next((index + 1 for index in range(header + 1, len(lines)) if lines[index] == "备注"), header + 1)
    rows: dict[str, tuple[int, int, int]] = {}
    index = start
    while index + 3 < len(lines):
        name = lines[index]
        values = lines[index + 1 : index + 4]
        if name and all(re.fullmatch(r"\d+", value) for value in values):
            rows[name] = tuple(int(value) for value in values)  # type: ignore[assignment]
            index += 4
        else:
            index += 1
    return rows if "合计" in rows else {}


def extract_value_creation_rows(text: str) -> list[dict[str, str]]:
    """Extract readable value-creation rows from one PDF page."""
    stages = ("方案设计", "初步设计", "施工图设计")
    symbols = {"+", "-", "/"}
    lines = [re.sub(r"\s+", "", line) for line in text.splitlines() if line.strip()]
    starts = []
    for index, line in enumerate(lines):
        if not re.fullmatch(r"\d+", line):
            continue
        stage_index = next((item for item in range(index + 2, min(len(lines), index + 6)) if any(stage in lines[item] for stage in stages)), None)
        if stage_index is not None:
            starts.append((index, stage_index))
    rows = []
    for row_index, (start, stage_index) in enumerate(starts):
        end = starts[row_index + 1][0] if row_index + 1 < len(starts) else len(lines)
        stage_line = lines[stage_index]
        stage = next(stage for stage in stages if stage in stage_line)
        location = stage_line.replace(stage, "").strip() or (lines[start + 2] if start + 2 < len(lines) else "")
        value_start = stage_index + 2
        effect_start = next((index for index in range(value_start, max(value_start, end - 5)) if all(lines[index + offset] in symbols for offset in range(6))), None)
        if effect_start is None or effect_start <= value_start:
            continue
        applicability = re.sub(r"第\d+页$", "", "".join(lines[effect_start + 6 : end])).strip()
        rows.append({
            "number": lines[start],
            "professional": lines[start + 1] if start + 1 < len(lines) else "",
            "location": location,
            "stage": stage,
            "business": lines[stage_index + 1] if stage_index + 1 < len(lines) else "",
            "value_item": "".join(lines[value_start:effect_start]).strip(),
            "applicability": applicability,
        })
    return rows
