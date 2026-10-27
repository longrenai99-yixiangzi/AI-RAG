"""A reference note can select an admitted body, but cannot become its evidence."""
import hashlib
from pathlib import Path
from urllib.parse import unquote
from app.ingestion.normalization.markdown_links import primary_source_link


def linked_path(text):
    link=primary_source_link(text)
    if not link or not link['complete']:return None
    value=unquote(link['target']).removeprefix('file:///')
    if value.startswith(('\\\\','//')) or not Path(value).is_absolute():return None
    return Path(value)


def binding_current(binding):
    try:
        return all(hashlib.sha256(Path(binding[p]).read_bytes()).hexdigest()==binding[v] for p,v in [('note_path','note_version'),('linked_path','linked_version'),('body_path','body_version')])
    except OSError:return False
