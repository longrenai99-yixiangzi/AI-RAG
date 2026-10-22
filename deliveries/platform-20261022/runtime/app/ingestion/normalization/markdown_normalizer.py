from __future__ import annotations

import re

_MARKDOWN_LINK_RE = re.compile(r"\[\[[^\]]+\]\]|!?\[[^\]]*\]\([^)]+\)|file://\S+|https?://\S+")


def strip_markdown_links(text: str) -> str:
    return _MARKDOWN_LINK_RE.sub("", text)


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


def is_source_reference_note(text: str) -> bool:
    """Recognize source-link registration notes without discarding short factual prose."""
    text=normalize_markdown_text(text)
    text=re.sub(r'\A---\n.*?\n---(?:\n|$)','',text,flags=re.S)
    source_line=re.compile(r'^\s*\*\*来源\*\*\s*[:：]\s*\[.*\]\(.*\)\s*$')
    if not any(source_line.fullmatch(line) for line in text.splitlines()):return False
    title_seen=False
    for line in text.splitlines():
        if source_line.fullmatch(line):continue
        if is_markdown_heading(line):
            if not title_seen:title_seen=True;continue
            if re.sub(r'^#+\s+','',line) in {'关联内容','相关内容'}:continue
            return False
        if re.sub(r'[\s*+\-:：]','',strip_markdown_links(line)):return False
    return True
