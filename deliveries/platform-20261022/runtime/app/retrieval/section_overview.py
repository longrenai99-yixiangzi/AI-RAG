"""Collect existing sibling narratives for an explicitly named parent topic."""
import re
import unicodedata

from app.retrieval.named_source_scope import path_key
from app.retrieval.section_scope import mark_scope


def comparison_required(question):
    # Asking for comparison criteria is a method lookup, not a comparison of actual objects.
    criteria = r'(?:比较|对比)(?:的)?(?:哪些|什么|哪几个|哪几项|哪几)\s*(?:方面|维度|指标|内容|因素)|(?:比较|对比)(?:标准|原则|方法|步骤|流程|依据|维度|指标)'
    if re.search(r'比较|对比',question) and re.search(r'甲乙|两种|两个|两者|[AB甲乙一二]方案|方案[AB甲乙一二]|(?:与|和).{0,25}(?:比较|对比)',question):
        return True
    remaining = re.sub(criteria, '', question)
    return bool(re.search(r'比较|对比|区别|异同|差异|发生.{0,4}变化', remaining))


def topic_key(text):
    text = unicodedata.normalize('NFKC', text).replace('管控', '管理')
    text = re.sub(r'^\s*(?:第[一二三四五六七八九十0-9]+[章节]|[0-9]+(?:\.[0-9]+)*[、.\s]*)', '', text)
    return ''.join(c for c in text if c.isalnum())


def collect_overview(question, primary, records):
    headings = [s.strip() for s in primary.get('heading_path', '').split(' > ')]
    # shortcut: only explicitly named parent topics; semantic topic expansion needs separate review.
    query = topic_key(question)
    # A leaf topic in the question takes precedence over its ancestors.
    matches = [i for i, title in enumerate(headings) if len(topic_key(title)) >= 4 and topic_key(title) in query]
    if not matches or max(matches) == len(headings)-1:
        return [], {'status': 'NOT_PARENT_OVERVIEW'}
    prefix = headings[:max(matches)+1]
    audit = {'status': 'PARENT_COVERAGE_UNVERIFIED', 'parent_heading': ' > '.join(prefix)}
    if re.search(r'多少|几人|几位|人数|合计|计算|占比|全部|所有|逐项|完整清单|专职|兼职|(?:19|20)\d{2}|今年|去年|截至', question) or comparison_required(question):
        return [], {**audit, 'reason': 'EXHAUSTIVE_NUMERIC_TEMPORAL_OR_COMPARISON'}
    if not re.search(r'哪些|什么|措施|做法|要点|如何|怎么', question):
        return [], {'status': 'NOT_PARENT_OVERVIEW'}
    identity = (path_key(primary['source_path']), primary['source_version'])
    rows = [dict(r, role='DIRECT') for r in records
            if (path_key(r['source_path']), r['source_version']) == identity
            and [s.strip() for s in r.get('heading_path', '').split(' > ')][:len(prefix)] == prefix]
    scoped = mark_scope(question, rows)
    if not rows or any('MISMATCH' in r.get('scope', {}).values() for r in scoped):
        return [], {**audit, 'reason': 'MISSING_OR_MISMATCHED_CHILDREN'}
    children = list(dict.fromkeys(r['heading_path'] for r in rows))
    narratives = []; seen = set(); tables = 0
    for r in scoped:
        if r.get('table_id') or (r.get('location') or {}).get('table_index') is not None:
            tables += 1; continue
        text = r.get('text', '').strip()
        key = (r['heading_path'], text)
        if text and key not in seen:
            narratives.append(r); seen.add(key)
    missing = [h for h in children if h not in {r['heading_path'] for r in narratives}]
    audit.update(child_headings=children, narrative_count=len(narratives), table_rows_not_selected=tables,
                 missing_narrative_headings=missing)
    if missing or not narratives or len(narratives) > 8 or sum(len(r['text']) for r in narratives) > 6000:
        return [], {**audit, 'reason': 'INCOMPLETE_OR_OVERSIZED_NARRATIVE_SET'}
    audit['status'] = 'PARENT_NARRATIVES_COLLECTED'
    for r in narratives:
        r.update(answer_usage='PRIMARY', chapter_coverage=audit,
                 display_location=r['heading_path'], retrieval_origin='SAME_VERSION_PARENT_NARRATIVES')
    return narratives, audit
