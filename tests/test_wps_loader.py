import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.ingestion.loaders.wps_loader import WPSLoadResult, WPSLoader


def test_wps_loader_opens_read_only_and_closes_word(monkeypatch, tmp_path):
    path = tmp_path / "minutes.wps"
    path.write_bytes(b"wps")
    calls = {}

    class Paragraphs:
        Count = 1

        @staticmethod
        def Item(index):
            return SimpleNamespace(Range=SimpleNamespace(Text="会议时间：2026年1月23日\r", Style=SimpleNamespace(NameLocal="Normal")))

    class Document:
        @staticmethod
        def Close(**kwargs):
            calls["closed"] = kwargs["SaveChanges"]

    Document.Paragraphs = Paragraphs()

    class Application:
        Visible = True
        DisplayAlerts = 1
        ScreenUpdating = True
        Documents = SimpleNamespace(Open=lambda *args, **kwargs: calls.update(open_kwargs=kwargs) or Document())

        @staticmethod
        def Quit():
            calls["quit"] = True

    win32com = ModuleType("win32com")
    client = ModuleType("win32com.client")
    client.DispatchEx = lambda name: Application()
    win32com.client = client
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    loaded = WPSLoader().load(path, "doc-id")

    assert loaded.status == "parsed"
    assert loaded.paragraphs[0]["text"] == "会议时间：2026年1月23日"
    assert calls["open_kwargs"]["ReadOnly"] is True
    assert calls["closed"] == 0
    assert calls["quit"] is True


def test_wps_source_flows_to_atomic_and_document_intelligence(monkeypatch, tmp_path):
    path = tmp_path / "minutes.wps"
    path.write_bytes(b"approved source bytes")
    rows = [{"paragraph_number": 1, "text": "会议时间：2026年1月23日", "style": "Normal"}]
    monkeypatch.setattr(WPSLoader, "load", lambda self, source, document_id: WPSLoadResult("parsed", rows))

    atomic = build_atomic_evidence(path, tmp_path)
    parsed = DocumentIntelligenceV2Builder(tmp_path).build([path], atomic["records"])

    assert atomic["status"] == "parsed"
    assert atomic["records"][0]["source_path"] == str(path)
    assert atomic["records"][0]["sha256"]
    assert parsed["documents"][0]["file_type"] == ".wps"
    assert parsed["documents"][0]["source_path"] == str(path)
    assert any(row["text"] == "会议时间：2026年1月23日" for row in parsed["paragraphs"])
