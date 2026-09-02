from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from app.ingestion.metadata.governance import GovernanceClassifier


def main() -> int:
    parser = argparse.ArgumentParser(description="Add provisional governance fields to the 100-question Gold YAML.")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("tests") / "gold_questions" / "full_corpus_gold_questions.yaml",
    )
    args = parser.parse_args()
    text = args.path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text) or {}
    questions = payload.get("questions", [])
    classifier = GovernanceClassifier()
    expected: dict[str, tuple[str, str, str]] = {}
    for item in questions:
        expected_files = item.get("expected_files") or []
        file_name = str(expected_files[0]) if expected_files else ""
        governance = classifier.classify(file_name=file_name)
        expected[str(item["id"])] = (
            governance.document_role,
            governance.authority_level,
            governance.usage_scene,
        )

    output: list[str] = []
    changed = 0
    for line in text.splitlines(keepends=True):
        match = re.search(r"- \{id:\s*([^,]+),", line)
        if not match:
            output.append(line)
            continue
        question_id = match.group(1).strip()
        role, authority, scene = expected[question_id]
        if ", difficulty:" not in line:
            raise ValueError(f"Unexpected Gold line format: {question_id}")
        line = re.sub(
            r", expected_document_role: '[^']*', expected_authority_level: '[^']*', expected_usage_scene: '[^']*'",
            "",
            line,
        )
        insert = (
            f", expected_document_role: '{role}'"
            f", expected_authority_level: '{authority}'"
            f", expected_usage_scene: '{scene}'"
        )
        output.append(line.replace(", difficulty:", insert + ", difficulty:", 1))
        changed += 1

    args.path.write_text("".join(output), encoding="utf-8")
    print(f"questions={len(questions)} changed={changed} path={args.path}")
    return 0 if changed == len(questions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
