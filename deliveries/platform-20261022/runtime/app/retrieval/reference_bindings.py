"""A reference note can select an admitted body, but cannot become its evidence."""
import hashlib,re
from pathlib import Path
from urllib.parse import unquote


def linked_path(text):
    links=re.findall(r'^\s*\*\*来源\*\*\s*[:：]\s*\[.*\]\((.*)\)\s*$',text,re.M)
    if len(links)!=1:return None
    value=unquote(links[0]).removeprefix('file:///')
    if value.startswith(('\\\\','//')) or not Path(value).is_absolute():return None
    return Path(value)


def binding_current(binding):
    try:
        return all(hashlib.sha256(Path(binding[p]).read_bytes()).hexdigest()==binding[v] for p,v in [('note_path','note_version'),('linked_path','linked_version'),('body_path','body_version')])
    except OSError:return False
