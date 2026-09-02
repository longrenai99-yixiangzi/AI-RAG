from __future__ import annotations

import re


def normalize_markdown_text(text: str) -> str:
    """Return deterministic Markdown text without removing meaningful blank lines."""

    text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    return "\n".join(lines).rstrip("\n")


def normalize_markdown_block(text: str) -> str:
    """Normalize a SourceBlock while retaining internal paragraph boundaries."""

    return normalize_markdown_text(text).strip()


def is_markdown_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}[ \t]+\S", line))
