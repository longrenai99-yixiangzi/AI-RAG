from pathlib import Path

from app.index_state import detect_changes, file_fingerprint


def test_index_state_detects_new_unchanged_modified_and_deleted(tmp_path: Path) -> None:
    current = tmp_path / "current.md"
    deleted = tmp_path / "deleted.md"
    current.write_text("one", encoding="utf-8")
    deleted.write_text("gone", encoding="utf-8")
    old_current = file_fingerprint(current).to_dict()
    old_deleted = file_fingerprint(deleted).to_dict()
    current.write_text("two", encoding="utf-8")

    statuses, _ = detect_changes(
        [current],
        {
            str(current).casefold(): {**old_current, "source_path": str(current)},
            str(deleted).casefold(): {**old_deleted, "source_path": str(deleted)},
        },
    )

    assert statuses[str(current)] == "modified"
    assert statuses[str(deleted)] == "deleted"
