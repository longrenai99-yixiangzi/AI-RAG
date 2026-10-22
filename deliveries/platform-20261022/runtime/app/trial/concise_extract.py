"""Local structural extracts, never a question-to-answer registry or free-text generator."""
import re
import hashlib
from pathlib import Path


MARKER = re.compile(r'\[/body/p\[@paraId=[A-Za-z0-9]+\]\]\s*')
PARALLEL = re.compile(r'第([一二三四五六七八九十])[，、](?:是)?|([一二三四五六七八九十])是')
LIMITS = r'如果|若|仅|只(?:能|可|限|适用)|不得|不能|不应|不含|不包括|不适用|不宜|不负责|不承担|禁止|除非|至少|最多|不超过|不少于|暂估|暂定|约(?:为)?(?=\s*[\d一二三四五六七八九十百])|前提|否则|但|未明确|无法确认|尚未|适用条件|例外|豁免'
PROTECTED = re.compile(LIMITS+r'|\d|[一二三四五六七八九十百]+(?:人|天|年|万元|亿元|个月)|当.{0,40}时|在.{0,40}(?:前|后|期间|阶段|条件下)')


def clean(text):
    return MARKER.sub('', text).strip()


def first_sentence(unit):
    # Keep a complete unit whenever shortening could hide a restriction, number or exception.
    if PROTECTED.search(unit):
        return unit
    return re.split(r'(?<=[。！？；])', unit, maxsplit=1)[0].strip()


def table_fields(text, target):
    lines = text.splitlines()
    headers = [s.split('：', 1)[1].split('|') for s in lines if s.startswith('表头：')]
    rows = [s.split('：', 1)[1].split('|') for s in lines if s.startswith('行：')]
    if len(headers) != 1 or len(rows) != 1 or len(headers[0]) != len(rows[0]):
        return None
    fields = [(k.strip(), v.strip()) for k,v in zip(headers[0], rows[0])]
    if target == 'DESIGN_STAGE_POSITION':
        values = dict(fields)
        required = ('阶段', '岗位', '人员配置数量', '专职/兼职')
        if all(values.get(k) for k in required):
            return '；'.join(f'{k}：{values[k]}' for k in required) + '。'
    if target == 'PROJECT_ORGANIZATION_TOTAL' and any(v == '合计' for _,v in fields):
        amounts = [v for _,v in fields if re.fullmatch(r'\d+人', v)]
        if len(amounts) == 1:
            return '原表合计：' + amounts[0] + '。'
    return None


def concise_text(text, question='', target=''):
    text = clean(text)
    table = table_fields(text, target)
    if table:
        return table, 'NATIVE_SINGLE_ROW_FIELDS'
    if target == 'LEAD_ROLE':
        clauses = re.split(r'[，。]', text)
        if len(clauses) > 1 and re.search(r'(?:配置|配备).{1,25}\d+人', clauses[0]):
            rest = text[len(clauses[0]):]
            # Numbers in the retained clause are allowed; keep other numbers/conditions intact.
            if not PROTECTED.search(rest):
                selected=clauses[:2] if re.search(r'负责|统筹|牵头',clauses[1]) else clauses[:1]
                return '，'.join(selected) + '。', 'NATIVE_ROLE_COUNT_CLAUSE'
    # Numeric queries without a native, scope-checked row are not summarized.
    if re.search(r'多少|几人|几位|人数|金额|合计|计算|占比', question):
        return text, 'FULL_SOURCE_FALLBACK'
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    paragraphs = [p for p in paragraphs if not re.match(r'^(?:#{1,6}\s|\d+\.\d+\s*[^。；：]{1,50}$)', p)]
    # An explicit actor heading can select its own block, never another actor's duties.
    labels = [(i,re.match(r'^([^：:。；]{2,20})[：:]', p)) for i,p in enumerate(paragraphs)]
    actors = [(i,m[1].removesuffix('层级').removesuffix('级')) for i,m in labels if m]
    matched = [(i,a) for i,a in actors if len(a)>=2 and a in question]
    if len(matched) == 1:
        index, actor = matched[0]
        contexts = []
        for p in paragraphs[:index]:
            if not re.match(r'^[^：:。；]{2,20}[：:]',p):
                contexts.extend(s.strip() for s in re.split(r'(?<=[。！？])',p)
                                if re.search(re.escape(actor)+r'(?:层级|级)?(?:负责|承担|侧重|提供|应|须|需|是|：|:)',s))
                if PROTECTED.search(p) and actor not in p:
                    contexts.append(p)
        block = paragraphs[index]
        guarded=[p for i,p in enumerate(paragraphs) if i!=index and PROTECTED.search(p) and not re.match(r'^[^：:。；]{2,20}[：:]',p)]
        selected = '\n'.join(dict.fromkeys([*contexts,block,*guarded]))
        if selected and len(selected) < len(text):
            return selected, 'EXPLICIT_ACTOR_BLOCK'
    for p in paragraphs:
        markers = list(PARALLEL.finditer(p))
        numbers = [m[1] or m[2] for m in markers]
        if len(markers) >= 2 and numbers == list('一二三四五六七八九十')[:len(markers)]:
            context = p[:markers[0].start()].strip()
            # Cross-paragraph restrictions cannot be inferred to be irrelevant.
            guarded = [v for v in paragraphs if v != p and PROTECTED.search(v)]
            if context and PROTECTED.search(context):
                guarded.append(context)
            units = [p[m.start():markers[i+1].start() if i+1<len(markers) else len(p)].strip() for i,m in enumerate(markers)]
            return '\n'.join([*guarded, *(first_sentence(u) for u in units)]), 'COMPLETE_PARALLEL_ITEMS'
    children = next((i for i,p in enumerate(paragraphs) if re.match(r'^[（(]\d+[）)]',p)), None)
    if (children is not None and re.search(r'哪.*类|哪些|哪几', question)
            and not re.search(r'阶段|年度|\d|期间|条件下|仅|专职|兼职',question)):
        overview = paragraphs[:children]
        if any('、' in p and re.search(r'包括|包含|涉及|如',p) for p in overview):
            children_text=paragraphs[children:]
            if any(re.search(LIMITS,p) for p in children_text):
                return text, 'FULL_SOURCE_FALLBACK'
            # An authored overview answers a general category question; child implementation examples stay in the full citation.
            return '\n'.join(overview), 'COMPLETE_LIST_OVERVIEW'
    return text, 'FULL_SOURCE_FALLBACK'


def readable_citations(cards):
    cache={}
    result=[]
    for c in cards:
        row=dict(c);path=Path(c.get('source_path',''))
        if path.suffix.lower()=='.md':
            key=(str(path),c.get('source_version'))
            if key not in cache:
                title=None
                try:
                    raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()==key[1]:
                        content=raw.decode('utf-8-sig')
                        match=re.search(r'^#\s+(.+)$',content,re.M)
                        derived=bool(re.search(r'^(?:source_path|source_file):|^\*\*来源\*\*[:：]',content,re.M))
                        if match:title=match[1].strip()+('（转换稿）' if derived else '（Markdown）')
                except (OSError,UnicodeError):pass
                cache[key]=title
            if cache[key]:row['display_file_name']=cache[key]
        result.append(row)
    return result
