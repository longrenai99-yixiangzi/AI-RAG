from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PDFQualityResult:
    """Read-only PDF quality metrics used to decide whether OCR is needed."""

    status: str
    total_pages: int
    page_text_lengths: list[int] = field(default_factory=list)
    page_image_counts: list[int] = field(default_factory=list)
    text_chars: int = 0
    text_pages: int = 0
    empty_text_pages: int = 0
    image_pages: int = 0
    image_count: int = 0
    image_page_ratio: float = 0.0
    suspected_scanned: bool = False
    reason: str | None = None


def assess_pdf(
    pdf: Any,
    *,
    min_text_chars_per_page: int = 20,
    min_text_page_ratio: float = 0.5,
    min_image_page_ratio: float = 0.5,
) -> PDFQualityResult:
    """Inspect text/image coverage without performing OCR or writing files."""

    total_pages = len(pdf)
    if total_pages == 0:
        return PDFQualityResult(status="empty", total_pages=0)

    page_text_lengths: list[int] = []
    page_image_counts: list[int] = []
    for page in pdf:
        text_length = len(page.get_text("text").strip())
        image_count = len(page.get_images(full=True))
        page_text_lengths.append(text_length)
        page_image_counts.append(image_count)

    text_chars = sum(page_text_lengths)
    text_pages = sum(length > 0 for length in page_text_lengths)
    empty_text_pages = total_pages - text_pages
    image_pages = sum(count > 0 for count in page_image_counts)
    image_count = sum(page_image_counts)
    image_page_ratio = image_pages / total_pages
    average_text_chars = text_chars / total_pages
    text_page_ratio = text_pages / total_pages
    image_heavy = image_page_ratio >= min_image_page_ratio
    low_text = average_text_chars < min_text_chars_per_page
    sparse_text = text_page_ratio < min_text_page_ratio
    suspected_scanned = bool(
        image_heavy and (text_chars == 0 or low_text or sparse_text)
    )

    if suspected_scanned:
        status = "needs_ocr"
        reason = "图片页占比高且可提取文字量不足，疑似扫描 PDF"
    elif text_chars == 0:
        status = "empty"
        reason = "未提取到文字，且未发现足以判断为扫描件的图片页"
    else:
        status = "parsed"
        reason = None

    return PDFQualityResult(
        status=status,
        total_pages=total_pages,
        page_text_lengths=page_text_lengths,
        page_image_counts=page_image_counts,
        text_chars=text_chars,
        text_pages=text_pages,
        empty_text_pages=empty_text_pages,
        image_pages=image_pages,
        image_count=image_count,
        image_page_ratio=image_page_ratio,
        suspected_scanned=suspected_scanned,
        reason=reason,
    )
