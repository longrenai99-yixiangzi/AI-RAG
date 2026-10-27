"""Bounded original-field answers for reviewed PDF rows, never inferred project facts."""
import re,json,hashlib,unicodedata
from pathlib import Path


def compact(text):return re.sub(r'\s+','',str(text))
def fields(row):return {compact(f['name']):f for f in row['fields']}


SUBJECTS={'设计内容','策划事项','管理需求','业务需求','合约包内容','评价内容','条款名称','名称','岗位','项目','资格条件','评审因素','条款内容','评分因素（偏差率）'}
PARENT_FIELDS={'区域','部位'}
FIELD_ALIASES={'实际得分':'评价得分','不足':'亮点与不足','评分标准':'评价标准','参考软件':'参考应用软件工具'}


def purpose(row):
    names=set(fields(row))
    if row.get('purpose','').startswith('PROJECT_EVALUATION'):return 'EVALUATION_RECORD'
    if '数字化路径' in names:return 'REFERENCE_WORKFLOW'
    if {'精装修承包人','总包（甲）'}<=names:return 'CASE_CHECKMARKS'
    if '主合同要求' in names:return 'CASE_MATERIALS'
    if '设计优化' in names or '策划内容' in names:return 'CASE_OPTIMIZATION'
    return 'TENDER_ORIGINAL_FIELDS'


def subjects(row):
    result=[]
    for name,f in fields(row).items():
        value=compact(f['raw_text'])
        if name in SUBJECTS and 2<=len(value)<=60:result.append(value)
        if name=='条款名称' and '（' in value:result.append(re.sub(r'（.*?）','',value))
        if name=='条款号' and value:result.append(value)
    return result


def select(question,rows):
    """Caller must restrict rows to one explicitly selected current source."""
    if not rows:return None
    if len({(r['source_path'],r['source_version']) for r in rows})!=1:return None
    q=compact(re.sub(r'《.*?》','',question));all_names=list(dict.fromkeys(name for r in rows for name in fields(r)))
    def hold(message,examples=()):
        return {'status':'CLARIFICATION','message':message,'rows':list(examples)[:3],'selected_fields':[]}
    if '条款号' in all_names:
        normalize=lambda s:unicodedata.normalize('NFKC',compact(s))
        codes=set(re.findall(r'(?<![\d.])\d+(?:\.\d+){1,4}(?:\(\d+\))?(?![\d.])',normalize(q)))
        if codes:
            exact=[r for r in rows if '条款号' in fields(r) and normalize(fields(r)['条款号']['raw_text']) in codes]
            if not exact:return None
            rows=exact
    evaluation=any(purpose(r)=='EVALUATION_RECORD' for r in rows)
    if re.search(r'通用(?:合同)?条件|专用(?:合同)?条件',q):return None
    if evaluation:
        years=set(re.findall(r'(20\d{2})年',q));dates={r.get('_source_context',{}).get('evaluation_date','') for r in rows}
        if years and (len(years)!=1 or len(dates)!=1 or not next(iter(dates)).startswith(next(iter(years)))):return hold('所问年份未与原表记录日期唯一对应，未将本次记录代作其他年份或全年结论。',rows[:1])
        if re.search(r'最新|现行|现在',q):return hold('本表只能证明所载日期的评价记录，未核定为最新或当前现场状态。',rows[:1])
    if evaluation and re.search(r'满分|标准总分|标准分合计',q):
        summary=[r for r in rows if r['row_type']=='EXPLICIT_MERGED_SUMMARY_NOT_COLUMN_SCORES']
        return hold('原表末行是评价综合得分，不能把该合并格当作标准总分；标准分合计需要逐项核算，本次字段摘录没有执行跨行计算。',summary)
    if evaluation and re.search(r'综合得分|实际总得分|总体评价得分',q):
        chosen=[r for r in rows if r['row_type']=='EXPLICIT_MERGED_SUMMARY_NOT_COLUMN_SCORES']
        return {'status':'READY','rows':chosen,'selected_fields':['评价综合得分'],'kind':'SUMMARY'} if len(chosen)==1 else hold('尚未唯一定位原表综合得分格。',chosen)
    if evaluation and re.search(r'未选|全部|完整|全文|所有(?:选项|评价|字段|工作项)',q):return hold('本批只核定指定原表行及已选字段，不能把片段当作整表或模板全文；完整原文可在引用原页查看。',rows[:1])
    if evaluation and re.search(r'实际配置|实际人数|团队总人数|设计团队总|专职人数|兼职人数',q):return hold('本表评分标准或记录不足以证明实际人员配置、团队总人数或专兼职人数。',rows[:1])
    candidates=[]
    for r in rows:
        anchors=[s for s in subjects(r) if s in q and (len(s)>=4 or re.search(re.escape(s)+r'(?:的|如何|怎么|是什么|原文|勾选|主合同|建议|[？?])',q))]
        # A partial clause number must not select a numbered subclause from another table.
        anchors=[s for s in anchors if not re.match(r'^\d',s) or re.search(r'(?<![\d.])'+re.escape(s)+r'(?![\d.（(])',q)]
        if anchors:candidates.append((anchors,r))
    if not candidates:
        if any(name in q for name in all_names if name in {'标准分','评价得分','亮点与不足','数字化路径','主合同要求','资格要求'}):
            return hold('请明确原表工作项或条款；本次未把某一行当作整表，也未执行跨行比较。',rows[:2])
        return None
    all_anchors={s for anchors,_ in candidates for s in anchors}
    maximal={s for s in all_anchors if not any(s!=other and s in other for other in all_anchors)}
    chosen=[r for anchors,r in candidates if any(s in maximal for s in anchors)]
    # Explicit parent labels distinguish otherwise identical work items across areas.
    for parent in PARENT_FIELDS:
        mentioned={compact(fields(r)[parent]['raw_text']) for r in rows if parent in fields(r) and compact(fields(r)[parent]['raw_text']) in q}
        if mentioned:chosen=[r for r in chosen if parent in fields(r) and compact(fields(r)[parent]['raw_text']) in mentioned]
    if not chosen:return hold('所问区域、部位与工作项未唯一对应，未改用其他行。')
    if any({'资格要求','数量'}<=set(fields(r)) for r in chosen) and re.search(r'实际|到岗|已配|专职|兼职|专兼职',q):
        return hold('本表列招标岗位资格和数量要求，不能证明实际到岗人数或专兼职情况。',chosen)
    years=set(re.findall(r'(20\d{2})年',q));dates={r.get('_source_context',{}).get('evaluation_date','') for r in chosen}
    if years and (len(years)!=1 or len(dates)!=1 or not next(iter(dates)).startswith(next(iter(years)))):
        return hold('所问年份未与原表记录日期唯一对应，未将本次记录代作其他年份或全年结论。',chosen)
    if re.search(r'现行|最新|法定|法律效力|所有项目|现在必须|实际配置|实际人数|团队总人数|专职人数|兼职人数|现在具备',q):return hold('本表记录、评分标准或招标要求不足以证明现行通用规则、实际人员配置或团队总人数。请限定原表字段或查看相应事实资料。',chosen)
    if re.search(r'未选|全部|完整|全文|所有选项',q):return hold('本批只核定指定原表行及已选字段，不把片段当作整表或模板全文。',chosen)
    explicit=[n for n in all_names if n in q and n not in SUBJECTS|PARENT_FIELDS and n not in {'序号','序号1','条款号'} and not n.startswith('原表')]
    if explicit:
        matching=[r for r in chosen if all(n in fields(r) for n in explicit)]
        if not matching:return hold('所问字段不属于所定位原行，未跨另一表借用同名事项的字段。',chosen)
        chosen=matching
    roots=[r for r in chosen if r.get('selected_root_option')]
    if roots and re.search(r'需要|缴|金额|要交',q) and '评审标准' not in q:chosen=roots
    # Remove known row/field names first, so conjunctions inside original names remain atomic.
    residual=q
    known=set(all_names)|set(FIELD_ALIASES)|{s for r in rows for s in subjects(r)}
    known|={compact(f['raw_text']) for r in rows for name,f in fields(r).items() if name in PARENT_FIELDS}
    for name in sorted(known,key=len,reverse=True):
        if name:residual=residual.replace(name,'')
    if re.search(r'和|以及|与|及|、|；',residual):
        rest=re.sub(r'根据|依据|请问|原表|本表|分别|是什么|是多少|多少|有哪些|中的|记录|原文|说明|工作|要求|内容|取值|勾选|是否|需要|缴纳|金额|的|是|为|及|与|和|以及|[\W\d_]','',residual)
        if len(rest)>=2:return hold('并列子问尚未全部对应到原表工作项或字段，未只回答命中的一部分。',chosen)
    p=purpose(chosen[0])
    if any(purpose(r)!=p for r in chosen):return hold('命中了不同用途的表段，请明确表名或页码。',chosen)
    if p.startswith('CASE_') and re.search(r'规范|统一要求|通用规定|必须',q):
        return hold('当前为项目案例表，不将优化记录、材料建议或勾选直接认定为通用规范要求。',chosen)
    # Fields are selected independently from row selection; explicit columns take precedence.
    asked=[n for n in all_names if len(n)>=2 and n in q and n not in SUBJECTS|PARENT_FIELDS and not n.startswith('原表') and n not in {'序号','序号1','条款号'}]
    for word,name in FIELD_ALIASES.items():
        if word in q and name in all_names and name not in asked and not (word=='评分标准' and '评分标准' in all_names):asked.append(name)
    if '得分' in q and not asked and '评价得分' in all_names:asked=['评价得分']
    for name in all_names:
        without_unit=re.sub(r'[（(](?:万元|元|%|分|人|日历天)[）)]$','',name)
        if without_unit!=name and without_unit in q and name not in asked:asked.append(name)
    if any(r.get('selected_root_option') for r in chosen):
        if len(chosen)!=1:return hold('根选项尚未唯一对应。',chosen)
        if re.search(r'实际|已经|已交|已缴|提交了|交了',q):return hold('该条可证明原表勾选的招标要求，不能证明款项实际提交或缴纳情况。',chosen)
        return {'status':'READY','rows':chosen,'selected_fields':[],'kind':'SELECTED_ROOT_OPTION'}
    if not asked:
        defaults={'REFERENCE_WORKFLOW':['数字化路径'],'CASE_OPTIMIZATION':['设计优化' if '设计优化' in all_names else '策划内容'],
            'CASE_MATERIALS':['主合同要求','建议使用或替换品牌'],'CASE_CHECKMARKS':['精装修承包人','总包（甲）']}
        asked=defaults.get(p,[])
    if not asked:return hold('请明确要查的原表字段；不以整行或评分标准代替所问事实。',chosen)
    if re.search(r'谁|哪个岗位|负责人是谁',q) and p!='CASE_CHECKMARKS':
        return hold('当前命中表段未提供可确认该负责人的原表字段，未从管理需求或软件名称反推岗位。',chosen)
    if len(chosen)>4:return hold('同名事项对应较多行，请进一步限定原表条目。',chosen)
    if len(chosen)>1 and p!='EVALUATION_RECORD':return hold('该工作项在不同区域或表段重复，请补充区域、阶段或页码。',chosen)
    for r in chosen:
        available=fields(r)
        if any(n not in available for n in asked):return hold('并列字段未全部存在于同一原表行。',chosen)
        if any(available[n]['read_status']=='IMAGE_REGION_NO_READABLE_NUMBER' for n in asked):
            return hold('原表该金额区域为图像覆盖，未取得可读数值；不恢复底层不可见文字，不填0，也不猜金额。',chosen)
        if p=='REFERENCE_WORKFLOW' and any('给排水设备' in f['raw_text'] for f in r['fields']) and any('空调系统管理'==s for s in subjects(r)):
            return hold('原表管理需求写空调系统管理，路径原文却写给排水设备；两列指向对象不同，暂不替作者改写或确认空调设备做法。',chosen)
        if p=='REFERENCE_WORKFLOW' and '自动' in q and any('手动更新' in f['raw_text'] for f in r['fields']):
            return hold('需求标题含自动更新，但路径原文写手动更新；不能据标题认定已经自动实现。',chosen)
    return {'status':'READY','rows':chosen,'selected_fields':list(dict.fromkeys(asked)),'kind':'FIELDS'}


def bundle(question,records,source_scoped):
    typed=[r for r in records if r.get('reviewed_table_row')]
    if not source_scoped or not typed:return None
    originals=[{**r['reviewed_table_row'],'_source_context':r.get('reviewed_table_context',{})} for r in typed];plan=select(question,originals)
    if plan is None:return None
    mapping={r['evidence_id']:r for r in typed};chosen=[]
    for original in plan['rows']:
        c=dict(mapping[original['evidence_id']]);c['answer_usage']='PRIMARY' if plan['status']=='READY' else 'BACKGROUND'
        c['reviewed_table_plan']={k:v for k,v in plan.items() if k!='rows'};chosen.append(c)
    return {'candidate_evidence':chosen,'bundle_status':'PRIMARY_SECTION_CANDIDATE' if plan['status']=='READY' else 'SOURCE_SCOPE_MISSING',
        'scope_mismatch_message':plan.get('message',''),'reviewed_table_audit':{k:v for k,v in plan.items() if k!='rows'}}


def answer(result):
    cards=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
    if not cards or not all(c.get('reviewed_table_row') for c in cards):return None
    identity=lambda p:str(p).replace('\\','/').casefold()
    if any(identity(c.get('source_path',''))!=identity(c['reviewed_table_row']['source_path']) or c.get('source_version')!=c['reviewed_table_row']['source_version'] for c in cards):
        return {**result,'answer_status':'SOURCE_VERSION_UNCONFIRMED','answer':'原表字段与引用文件或版本未对应，已停止答复，请重新核对来源。',
            'citations':[{**c,'answer_usage':'BACKGROUND'} for c in result.get('citations',[])],'generation_mode':'NO_GENERATION'}
    plans=[c.get('reviewed_table_plan',{}) for c in cards]
    if not all(p.get('status')=='READY' for p in plans):return None
    parts=[]
    for c,plan in zip(cards,plans):
        r=c['reviewed_table_row'];values=fields(r)
        title=' / '.join(s for s in subjects(r) if not re.match(r'^\d',s)) or '原表汇总'
        if r.get('original_project_name'):title='原表项目：'+r['original_project_name']+'；'+title
        if c.get('reviewed_table_context',{}).get('evaluation_date'):title+='（评价时间：'+c['reviewed_table_context']['evaluation_date']+'）'
        if plan['kind']=='SELECTED_ROOT_OPTION':
            content='该版原表根选项勾选“不要求”；后续未选“要求”分支中的示例金额不作为本项目已采用要求。'
        else:
            segments=[]
            for name in plan['selected_fields']:
                f=values[name];text=f['raw_text'].strip()
                if not text:text='原表该栏未填写（不等于0或没有该事项）'
                # The checked source branch is shown only when its source field has one checkmark.
                if text.lstrip().startswith(('☑','□')) and text.count('☑')==1 and '□' in text and not r.get('selected_root_option'):
                    text=next(p for p in re.split(r'(?=[☑□])',text) if p.startswith('☑')).strip()
                segments.append(name+'：'+text)
            content='\n'.join(segments)
        parts.append(title+'\n'+content+f' [{c["citation_id"]}]')
    return {**result,'answer_status':'SOURCE_EXTRACT','answer':'\n\n'.join(parts),'status_label':'已核原表字段 · 待业务核对',
        'generation_mode':'REVIEWED_TABLE_FIELDS_NO_MODEL','notice':'仅据本版原表字段摘录；空白不填0，未选分支不当已采用要求，不由评分反推实际人数。'}
