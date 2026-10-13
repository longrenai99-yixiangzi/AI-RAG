"""Read a named document without borrowing facts from similarly titled files."""
import re
import unicodedata


def overview_title(question: str) -> str:
    match = re.fullmatch(r'(?:请)?《([^》]{2,260})》(?:这份)?(?:资料|文件|课件|报告)?的?(?:主要讲了什么|讲了什么|主要内容是什么)[？?。]?(?:请(?:给出|概括|总结)(?:其中的)?(?:关键|主要)内容[。？?]?)?', question.strip())
    return match[1] if match else ''


def file_key(name: str, *, stem: bool = True) -> str:
    name = unicodedata.normalize('NFKC', str(name)).replace('\\','/').casefold()
    if stem:
        name = re.sub(r'\.(?:pdf|pptx?|docx?|xlsx?|md|txt|wps)$', '', name)
    name = re.sub(r'^\d+(?:[.、](?!\d)|\s+)', '', name)
    return re.sub(r'\s+', '', name)


def named_document_ids(documents: dict, title: str) -> set[str]:
    explicit_extension = bool(re.search(r'\.(?:pdf|pptx?|docx?|xlsx?|md|txt|wps)$', title, re.I))
    key = file_key(title, stem=not explicit_extension)
    if '/' in title or '\\' in title:
        return {did for did,doc in documents.items() if file_key(doc.get('source_path',''),stem=not explicit_extension)==key}
    return {did for did, doc in documents.items() if file_key(doc.get('file_name', ''), stem=not explicit_extension) == key}


def overview_records(atomic: dict, document_ids: set[str], allowed_ids: set[str] | None) -> list[dict]:
    from app.ingestion.atomic_search import search_record_role
    from scripts.build_verified_evidence_bundle_v1 import _link_only
    groups = {}
    for eid, record in atomic.items():
        if record.get('document_id') not in document_ids or allowed_ids is not None and eid not in allowed_ids:
            continue
        raw = str(record.get('raw_text') or record.get('text') or '')
        path = str(record.get('source_path') or '').replace('\\','/').casefold()
        if not record.get('source_version') or '/wiki/queries/' in path or search_record_role(record) != 'PRIMARY_BODY' or _link_only(raw):
            continue
        groups.setdefault((record['document_id'], record['source_version']), []).append(record)
    versions = {}
    for (_, version), records in groups.items():
        if len(records) > len(versions.get(version, [])):
            versions[version] = records
    if len(versions) > 1:
        return [{**records[0], 'overview_context': {'ambiguous': True}} for records in versions.values()]
    if not versions:
        return []
    records = next(iter(versions.values()))
    form = bool(re.search(r'报名表|调查表|登记表|审批表', records[0].get('file_name', '')))
    sections = {}
    for record in records:
        raw = str(record.get('raw_text') or record.get('text') or '').strip()
        if form:
            header = re.search(r'^表头[：:]([^\n]+)', raw, re.M)
            if not header:
                continue
            raw = '表头：' + header[1].strip()
        elif len(re.sub(r'\s+', '', raw)) < 60 or re.match(r'^(?:目录|contents\b)', raw, re.I):
            continue
        location = record.get('location') or {}
        key = record.get('table_id') if form else (record.get('heading_path') or location.get('page') or '正文')
        if key not in sections or len(raw) > len(sections[key]['text_override']):
            sections[key] = {**record, 'text_override': raw, 'raw_text_override': raw,
                             'overview_context': {'ambiguous': False, 'form_headers_only': form}}
    return list(sections.values())[:6]
