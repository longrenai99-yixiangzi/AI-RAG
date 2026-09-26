from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class WPSLoadResult:
    status: str
    paragraphs: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None


class WPSLoader:
    """Read WPS through installed Word-compatible COM automation without saving the source."""

    def load(self, path: Path, document_id: str) -> WPSLoadResult:
        if path.suffix.casefold() != ".wps":
            return WPSLoadResult("read_error", error=f"不支持的文件扩展名：{path.suffix or '无扩展名'}")

        app = document = None
        try:
            from win32com.client import DispatchEx

            app = DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            app.ScreenUpdating = False
            document = app.Documents.Open(
                str(path),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                NoEncodingDialog=True,
            )
            paragraphs = []
            for number in range(1, int(document.Paragraphs.Count) + 1):
                paragraph = document.Paragraphs.Item(number)
                text = str(paragraph.Range.Text or "").replace("\x07", "").replace("\x0b", "\n").strip("\r\n\t ")
                if not text:
                    continue
                try:
                    style = str(paragraph.Range.Style.NameLocal)
                except Exception:
                    style = "Normal"
                paragraphs.append({"document_id": document_id, "paragraph_number": number, "text": text, "style": style})
            return WPSLoadResult("parsed" if paragraphs else "empty", paragraphs)
        except Exception as error:
            return WPSLoadResult("read_error", error=f"{type(error).__name__}: {error}")
        finally:
            if document is not None:
                try:
                    document.Close(SaveChanges=0)
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
