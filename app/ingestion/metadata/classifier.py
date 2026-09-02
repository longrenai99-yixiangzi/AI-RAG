from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from app.ingestion.metadata.schema import MetadataRecord


class MetadataClassifier:
    """Config-driven first-pass Metadata classifier with explicit confidence."""

    def __init__(self, rules_path: Path | None = None) -> None:
        self.rules_path = rules_path or Path(__file__).with_name("rules.yaml")
        self.rules = yaml.safe_load(self.rules_path.read_text(encoding="utf-8")) or {}
        self.auto_min_confidence = float(
            self.rules.get("review", {}).get("auto_min_confidence", 0.8)
        )

    def classify(
        self,
        path: Path,
        root: Path,
        *,
        parse_status: str,
        title: str = "",
        headers: Iterable[str] = (),
        text: str = "",
        front_matter: Mapping[str, Any] | None = None,
    ) -> MetadataRecord:
        front_matter = front_matter or {}
        evidence = {
            "path": self._relative_path(path, root),
            "file_name": path.name,
            "title": title,
            "headers": " ".join(headers),
            "body": text,
        }
        values: dict[str, str | None] = {}
        sources: dict[str, str] = {}
        rules: dict[str, str] = {}
        confidence: dict[str, float] = {}
        needs_review = parse_status not in {"parsed", "empty"}

        for field_name, field_rules in self.rules.get("fields", {}).items():
            value, source, rule_id, score = self._classify_field(
                field_name, field_rules, evidence, front_matter
            )
            values[field_name] = value
            sources[field_name] = source
            rules[field_name] = rule_id
            confidence[field_name] = score
            if value is None or score < self.auto_min_confidence:
                needs_review = True

        return MetadataRecord(
            file_type=path.suffix.lower(),
            file_name=path.name,
            source_path=str(path),
            sha256=_sha256(path),
            parse_status=parse_status,
            board=values.get("board"),
            knowledge_type=values.get("knowledge_type"),
            discipline=values.get("discipline"),
            metadata_source=sources,
            metadata_rule=rules,
            metadata_confidence=confidence,
            metadata_review_status="NEEDS_REVIEW" if needs_review else "AUTO",
        )

    @staticmethod
    def _classify_field(
        field_name: str,
        field_rules: dict,
        evidence: dict[str, str],
        front_matter: Mapping[str, Any],
    ) -> tuple[str | None, str, str, float]:
        for source in field_rules.get("source_priority", []):
            if source == "front_matter":
                keys = field_rules.get("front_matter_keys", [field_name])
                haystack = " ".join(
                    _flatten_front_matter(front_matter.get(key)) for key in keys
                ).lower()
            else:
                haystack = evidence.get(source, "").lower()
            if not haystack:
                continue
            for rule in field_rules.get("rules", []):
                if any(str(keyword).lower() in haystack for keyword in rule.get("keywords", [])):
                    default_score = 1.0 if source == "front_matter" else 0.0
                    score = float(rule.get("confidence", {}).get(source, default_score))
                    return rule.get("value"), source, rule.get("id", "unknown_rule"), score
        return None, "unmatched", "no_match", 0.0

    @staticmethod
    def _relative_path(path: Path, root: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)


def classify_metadata(
    path: Path,
    root: Path,
    *,
    parse_status: str,
    title: str = "",
    headers: Iterable[str] = (),
    text: str = "",
    front_matter: Mapping[str, Any] | None = None,
) -> MetadataRecord:
    return MetadataClassifier().classify(
        path,
        root,
        parse_status=parse_status,
        title=title,
        headers=headers,
        text=text,
        front_matter=front_matter,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1_048_576), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest()


def _flatten_front_matter(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_front_matter(item) for item in value)
    if isinstance(value, Mapping):
        return " ".join(
            f"{key} {_flatten_front_matter(item)}" for key, item in value.items()
        )
    return str(value)
