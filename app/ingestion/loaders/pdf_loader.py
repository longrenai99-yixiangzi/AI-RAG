from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
