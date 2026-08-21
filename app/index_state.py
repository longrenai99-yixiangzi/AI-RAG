from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class FileFingerprint:
    path: str
    size: int
    mtime_ns: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def file_fingerprint(path: Path) -> FileFingerprint:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return FileFingerprint(str(path), stat.st_size, stat.st_mtime_ns, digest.hexdigest())


def detect_changes(
    paths: Iterable[Path], previous: dict[str, dict[str, Any]]
) -> tuple[dict[str, str], dict[str, FileFingerprint]]:
    """Detect changes while preserving the full rebuild path for V0.2."""
    current: dict[str, FileFingerprint] = {}
    statuses: dict[str, str] = {}
    for path in paths:
        fingerprint = file_fingerprint(path)
        key = str(path).casefold()
        current[key] = fingerprint
        old = previous.get(key) or previous.get(str(path))
        if old is None:
            statuses[str(path)] = "new"
        elif (
            int(old.get("file_size", old.get("size", -1))) == fingerprint.size
            and int(old.get("mtime_ns", -1)) == fingerprint.mtime_ns
            and str(old.get("sha256", "")) == fingerprint.sha256
        ):
            statuses[str(path)] = "unchanged"
        else:
            statuses[str(path)] = "modified"
    for key, old in previous.items():
        if key not in current:
            statuses[str(old.get("source_path", key))] = "deleted"
    return statuses, current
