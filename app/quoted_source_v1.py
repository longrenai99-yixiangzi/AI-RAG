"""Locate a supplied excerpt without treating its numbers as verified facts."""
import re
import unicodedata


def quoted_statement(question: str) -> str:
    match = re.fullmatch(r'(.{8,900}?)[—－-]{2,}\s*这个(?:数据|数字|内容|说法|条文)出自哪份资料[、，,]?具体是多少[？?]?', question.strip())
    return match[1].strip() if match else ''


def compact_excerpt(text: str) -> str:
    return re.sub(r'[^\w.%]', '', unicodedata.normalize('NFKC', text).casefold()).replace('_', '')


def source_reading_records(parsed: dict, indexed: dict) -> dict:
    def key(row, version):return (str(row.get('source_path') or '').replace('\\','/').casefold(), version, row.get('document_id'))
    anchors = {key(r,r.get('source_version')): r for r in indexed.values() if r.get('source_version')}
    records = {}
    for eid, row in parsed.items():
        version = row.get('source_version') or row.get('sha256')
        anchor = anchors.get(key(row,version))
        if anchor:
            location = dict(row.get('location') or {})
            if location.get('slide') and not location.get('page'):
                location['page'] = location['slide']
            records[eid] = {**row, 'source_id':anchor.get('source_id'), 'source_version':version, 'location':location, 'lineage_status':'LINEAGE_CONFIRMED'}
    return records


def quoted_source_records(atomic: dict, statement: str, allowed_ids: set | None) -> list[dict]:
    from app.ingestion.atomic_search import search_record_role
    from scripts.build_verified_evidence_bundle_v1 import _link_only
    target = compact_excerpt(statement)
    if len(target) < 8:
        return []
    versions = {}
    for eid, record in atomic.items():
        if allowed_ids is not None and eid not in allowed_ids:
            continue
        raw = str(record.get('raw_text') or record.get('text') or '')
        if not record.get('source_version') or target not in compact_excerpt(raw):
            continue
        path = str(record.get('source_path') or '').replace('\\', '/').casefold()
        if '/wiki/queries/' in path or search_record_role(record) not in {'PRIMARY_BODY', 'NAVIGATION'} or _link_only(raw):
            continue
        key = (path, record['source_version'])
        if key not in versions or len(raw) < len(versions[key].get('raw_text') or versions[key].get('text') or ''):
            versions[key] = record
    # shortcut: return a bounded source excerpt, not a full semantic summary; expand only with verified source context.
    selected = []
    for record in sorted(versions.values(), key=lambda r: (str(r.get('source_path')), r['source_version']))[:4]:
        raw = str(record.get('raw_text') or record.get('text') or '')
        if len(raw) > 2400:
            positions = [i for i, char in enumerate(raw) for _ in compact_excerpt(char)]
            normalized = compact_excerpt(raw)
            if len(positions) != len(normalized):
                continue
            start = normalized.find(target)
            raw = raw[max(0, positions[start]-300):positions[start+len(target)-1]+901]
        selected.append({**record, 'text_override': raw, 'raw_text_override': raw})
    return selected
