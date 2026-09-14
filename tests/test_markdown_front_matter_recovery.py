from app.ingestion.loaders.markdown_loader import MarkdownLoader


def test_recover_windows_path_front_matter(tmp_path) -> None:
    path = tmp_path / "source.md"
    path.write_text("---\ntype: approved_external_source\nsource_path: \"D:\\\\工作\\\\source.pdf\"\n---\n\n# Body\n\n事实正文。\n", encoding="utf-8")
    result = MarkdownLoader().load(path, "doc-1")
    assert result.status == "parsed"
    assert result.front_matter["source_path"] == "[LOCAL_PATH_REDACTED]"
    assert "事实正文" in result.blocks[0].text
