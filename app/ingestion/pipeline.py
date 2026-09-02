from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from app.chunker import chunk_blocks
from app.domain import Chunk, SourceBlock
from app.ingestion.loaders.docx_loader import DOCXLoader
from app.ingestion.loaders.markdown_loader import MarkdownLoader
from app.ingestion.loaders.pdf_loader import PDFLoader
from app.ingestion.loaders.ppt_loader import PPTLoader
from app.ingestion.loaders.xlsx_loader import XLSXLoader
from app.ingestion.metadata.classifier import MetadataClassifier
from app.ingestion.metadata.validator import validate_metadata
from app.ingestion.staging import build_staging_record
from app.parsers import iter_source_files


LOADERS = {
    ".md": MarkdownLoader,
    ".markdown": MarkdownLoader,
    ".pptx": PPTLoader,
    ".pdf": PDFLoader,
    ".docx": DOCXLoader,
    ".xlsx": XLSXLoader,
}
METADATA_CLASSIFIER = MetadataClassifier()


@dataclass(slots=True)
class PipelineDocument:
    path: Path
    file_type: str
    status: str
    source_blocks: list[SourceBlock] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    quality: dict[str, Any] | None = None
    error: str | None = None

    def staging_json(self) -> dict[str, Any]:
        return build_staging_record(
            status=self.status,
            source_blocks=self.source_blocks,
            chunks=self.chunks,
            metadata=self.metadata,
            chunk_metadata=self.chunk_metadata,
            error=self.error,
        )


@dataclass(slots=True)
class PipelineResult:
    root: Path
    documents: list[PipelineDocument]
    scan_errors: list[str] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def source_block_count(self) -> int:
        return sum(len(document.source_blocks) for document in self.documents)

    @property
    def chunk_count(self) -> int:
        return sum(len(document.chunks) for document in self.documents)

    def status_counts(self) -> dict[str, int]:
        return dict(Counter(document.status for document in self.documents))

    def file_type_counts(self) -> dict[str, int]:
        return dict(Counter(document.file_type for document in self.documents))

    def metadata_complete_chunk_count(self) -> int:
        return sum(
            1
            for document in self.documents
            for metadata in document.chunk_metadata.values()
            if metadata_is_complete(metadata)
        )

    def location_valid_chunk_count(self) -> int:
        return sum(
            1
            for document in self.documents
            for chunk in document.chunks
            if location_is_valid(document.file_type, chunk.location)
        )

    def validation_summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "scanned_files": self.scanned_files,
            "documents": len(self.documents),
            "source_blocks": self.source_block_count,
            "chunks": self.chunk_count,
            "metadata_complete_chunks": self.metadata_complete_chunk_count(),
            "location_valid_chunks": self.location_valid_chunk_count(),
            "status_counts": self.status_counts(),
            "file_type_counts": self.file_type_counts(),
            "scan_errors": self.scan_errors,
            "documents_detail": [
                {
                    "path": str(document.path),
                    "file_type": document.file_type,
                    "status": document.status,
                    "source_blocks": len(document.source_blocks),
                    "chunks": len(document.chunks),
                    "metadata_complete": metadata_is_complete(document.metadata),
                    "location_valid_chunks": sum(
                        location_is_valid(document.file_type, chunk.location)
                        for chunk in document.chunks
                    ),
                    "quality": document.quality,
                    "error": document.error,
                }
                for document in self.documents
            ],
        }


def build_metadata(
    path: Path,
    root: Path,
    *,
    parse_status: str = "parsed",
    title: str = "",
    headers: Iterable[str] = (),
    text: str = "",
    front_matter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for the formal config-driven Metadata classifier."""

    return METADATA_CLASSIFIER.classify(
        path,
        root,
        parse_status=parse_status,
        title=title,
        headers=headers,
        text=text,
        front_matter=front_matter,
    ).to_dict()


def run_document_pipeline(
    root: Path,
    *,
    files: Iterable[Path] | None = None,
    limit_per_type: int | None = None,
) -> PipelineResult:
    """Run the new Loader -> SourceBlock -> Chunk -> Metadata validation path only."""

    scan_errors: list[str] = []
    candidates = list(files) if files is not None else iter_source_files(root, scan_errors=scan_errors)
    candidates = [path for path in candidates if path.suffix.lower() in LOADERS]
    candidates = _limit_by_type(candidates, limit_per_type)
    documents = [_process_file(path, root) for path in candidates]
    return PipelineResult(
        root=root,
        documents=documents,
        scan_errors=scan_errors,
        scanned_files=len(candidates),
    )


def _process_file(path: Path, root: Path) -> PipelineDocument:
    file_type = path.suffix.lower()
    loader = LOADERS[file_type]()
    result = loader.load(path, document_id=_document_id(path))
    blocks = list(result.blocks)
    chunks = chunk_blocks(blocks)
    title = next((block.heading_path for block in blocks if block.heading_path), "")
    text = "\n".join(block.text for block in blocks)[:4_000]
    front_matter = getattr(result, "front_matter", None)
    metadata = build_metadata(
        path,
        root,
        parse_status=result.status,
        title=title,
        text=text,
        front_matter=front_matter,
    )
    chunk_metadata = {chunk.chunk_id: dict(metadata) for chunk in chunks}
    quality = getattr(result, "quality", None)
    if is_dataclass(quality):
        quality = asdict(quality)
    return PipelineDocument(
        path=path,
        file_type=file_type,
        status=result.status,
        source_blocks=blocks,
        chunks=chunks,
        metadata=metadata,
        chunk_metadata=chunk_metadata,
        quality=quality,
        error=result.error,
    )


def metadata_is_complete(metadata: dict[str, Any]) -> bool:
    return validate_metadata(metadata).valid


def location_is_valid(file_type: str, location: dict[str, Any]) -> bool:
    if not location:
        return False
    if file_type in {".md", ".markdown"}:
        return _positive_range(location, "line_start", "line_end")
    if file_type == ".pptx":
        return isinstance(location.get("slide"), int) and location["slide"] > 0
    if file_type == ".pdf":
        return isinstance(location.get("page"), int) and location["page"] > 0
    if file_type == ".docx":
        return (
            _positive_range(location, "paragraph_start", "paragraph_end")
            or isinstance(location.get("table"), int)
            and location["table"] > 0
        )
    if file_type == ".xlsx":
        return (
            bool(location.get("sheet_name"))
            and _positive_range(location, "row_start", "row_end")
            and isinstance(location.get("column_count"), int)
            and location["column_count"] > 0
        )
    return False


def _positive_range(location: dict[str, Any], start: str, end: str) -> bool:
    return (
        isinstance(location.get(start), int)
        and isinstance(location.get(end), int)
        and location[start] > 0
        and location[end] >= location[start]
    )


def _limit_by_type(paths: list[Path], limit_per_type: int | None) -> list[Path]:
    if limit_per_type is None:
        return sorted(paths, key=lambda path: str(path).lower())
    if limit_per_type < 1:
        raise ValueError("limit_per_type must be positive")
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(paths, key=lambda item: str(item).lower()):
        grouped[path.suffix.lower()].append(path)
    return [path for suffix in sorted(grouped) for path in grouped[suffix][:limit_per_type]]


def _document_id(path: Path) -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve()).lower()))
