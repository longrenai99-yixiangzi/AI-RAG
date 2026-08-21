from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class OCRResult:
    text: str
    provider: str
    error: str | None = None


class OCRProvider(Protocol):
    name: str

    def extract(self, path: Path) -> OCRResult:
        """Return OCR text without changing the source file."""


class DisabledOCRProvider:
    name = "disabled"

    def extract(self, path: Path) -> OCRResult:
        return OCRResult(
            text="",
            provider=self.name,
            error=f"未启用 OCR：{path.name} 未建立有效文字层。",
        )


class PaddleOCRProvider:
    """Optional adapter; PaddleOCR remains an opt-in dependency."""

    name = "paddleocr"

    def __init__(self) -> None:
        self._engine: object | None = None

    def _load(self) -> object:
        if self._engine is None:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]

            self._engine = PaddleOCR(use_angle_cls=True, lang="ch")
        return self._engine

    @staticmethod
    def _flatten(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            result: list[str] = []
            for item in value:
                result.extend(PaddleOCRProvider._flatten(item))
            return result
        return []

    def extract(self, path: Path) -> OCRResult:
        try:
            engine = self._load()
            raw = engine.ocr(str(path), cls=True)  # type: ignore[attr-defined]
            text = "\n".join(part.strip() for part in self._flatten(raw) if part.strip())
            if not text:
                return OCRResult("", self.name, "OCR 未提取到有效文字。")
            return OCRResult(text, self.name)
        except Exception as error:
            return OCRResult("", self.name, f"{type(error).__name__}: {error}")


def build_ocr_provider(name: str) -> OCRProvider:
    normalized = (name or "disabled").strip().lower()
    if normalized in {"paddle", "paddleocr"}:
        return PaddleOCRProvider()
    return DisabledOCRProvider()
