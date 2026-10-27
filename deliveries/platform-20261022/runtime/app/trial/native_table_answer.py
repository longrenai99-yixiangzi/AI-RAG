"""Answer only an explicit native table field, preserving the full original condition."""
import re


def native_field_answer(result,question):
    cards=result.get('citations',[]);primary=[c for c in cards if c.get('answer_usage')=='PRIMARY']
    rows=[c for c in primary if c.get('native_pdf_table')]
    if not rows:return None
    from app.retrieval.named_source_scope import named_titles
    task=question
    for title in named_titles(question) or []:task=task.replace('《'+title+'》','')
    if any(c['native_pdf_table'].get('header_only') for c in rows):
        card=rows[0];meta=card['native_pdf_table'];headers=meta['all_original_headers'];names=list(dict.fromkeys(headers))
        if re.search(r'含义|解释|用途|填写|必填|选填|可不填',task):
            return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','answer':'本次只核对原表表头，不能据此确认字段含义或填写规则。',
                    'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards],'generation_mode':'NO_GENERATION','claims':[]}
        answer='表头名称：'+'、'.join(names)+'。'
        if len(names)!=len(headers):answer+=f' 原表有{len(headers)}个物理列，部分表头跨列合并；未另造字段名称。'
        return {**result,'answer_status':'SOURCE_EXTRACT','status_label':'原表表头 · 待核对','answer':answer+'\n['+card['citation_id']+']','generation_mode':'NATIVE_TABLE_HEADER_NO_MODEL'}
    specific=bool(len(rows)==1 and (rows[0]['native_pdf_table'].get('explicit_row_selection') or any(a in re.sub(r'\s+','',task) for a in rows[0]['native_pdf_table'].get('row_anchors',[]))))
    field='实际得分' if re.search(r'实际得分|实际分数|实得分|实际总分|实际总得分',task) else '标准分值' if re.search(r'标准分值|标准分|满分',task) else '评分标准' if re.search(r'扣几分|扣多少分|如何扣分|评分标准|扣分标准',task) else None
    if field is None and specific:
        choices=[('应对措施',r'措施'),('应对策略',r'策略'),('风险描述',r'定义|特征|描述|什么是'),('评价主体',r'评价主体|原表主体'),('评价事项',r'内容|包括|包含|事项|公式')]
        available=rows[0]['table_evidence']['headers']
        field=next((name for name,pattern in choices if name in available and re.search(pattern,task)),None)

    def refuse(message,reason):
        return {**result,'answer_status':'EVIDENCE_INSUFFICIENT','status_label':'原表字段或范围尚未核定','answer':message,
                'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards],'claims':[],'generation_mode':'NO_GENERATION',
                'native_table_field_audit':{'field':field,'reason':reason}}
    fields=dict(zip(rows[0]['table_evidence']['headers'],rows[0]['table_evidence']['values'])) if len(rows)==1 else {}
    if field is None and re.search(r'得分|分数',task):
        return refuse('请区分标准分值、扣分规则和实际得分；不能将标准分值或满分直接套作实得分。','AMBIGUOUS_SCORE_FIELD')
    formula_lookup=field=='评价事项' and '=' in fields.get(field,'') and '实际' not in task and not re.search(r'\d',re.sub(r'附件\d+|表[\d-]+','',task))
    explicit_total=bool(len(rows)==1 and rows[0]['native_pdf_table'].get('summary_row') and field in {'标准分值','实际得分'})
    if (re.search(r'合计|总扣分|总得分|平均|得分率|整体得分|实际总分|换算|比较|对比',task) and not explicit_total) or '计算' in task and not formula_lookup:
        return refuse('本次只核对原表字段，不据单行或未填写的评分栏推算实际总分、比率或跨行合计。','NO_UNVERIFIED_CALCULATION')
    if re.search(r'哪些|哪几|完整|全部',task) and not specific and not result.get('debug',{}).get('native_table_overview_audit',{}).get('complete_rows_included'):
        return refuse('当前选中的原表行不足以代表完整清单；请查看完整原表或进一步限定评价事项。','NO_SINGLE_ROW_AS_WHOLE_TABLE')
    if field is None:return None
    if len(rows)!=1 or len(primary)!=1:return refuse('尚未核定所问的唯一原表行，不能把不同事项或不同表的分值混用。','ROW_NOT_UNIQUE')
    card=rows[0];meta=card['native_pdf_table']
    if field not in fields:return refuse('当前原表没有所问字段，不能使用其他列的数值替代。','FIELD_NOT_PRESENT')
    if not fields[field]:return refuse(f'引用原表的“{field}”栏未填写，资料不足以确认该数值；标准分值和扣分规则不能代替实际得分。','EMPTY_FIELD_NOT_ZERO')
    for conflict in meta.get('field_term_conflicts',[]):
        if field==conflict['right_field'] and conflict['left_term'] in task and conflict['right_term'] not in task:
            if re.search(r'扣几分|扣多少|如何扣|该扣|应扣|是否|能否',task):
                return refuse('该行评分标准原文：'+fields[field]+'\n['+card['citation_id']+']\n'+f'原表“{conflict["left_field"]}”使用“{conflict["left_term"]}”，“{conflict["right_field"]}”使用“{conflict["right_term"]}”；本次保留同一行原文，但不将两个术语自动等同后判定具体扣分。','ORIGINAL_FIELD_TERM_CONFLICT')
    if field=='标准分值' and not specific:
        grouped=bool(meta.get('item_group_label') and meta['item_group_label'] in re.sub(r'\s+','',task))
        if not (grouped and meta.get('shared_standard_score') or meta.get('summary_row') and meta.get('explicit_table_selection')):
            return refuse('该评价事项可能跨多个评分子行；当前单行标准分值不能直接代表整项满分。请限定具体评分事项，或查阅原表各子项及合并分值。','SUBROW_SCORE_NOT_GROUP_TOTAL')
    if field=='评分标准' and not specific and meta.get('item_group_rows',1)>1:
        return refuse('该评价事项跨多个评分子行，当前单行不能代表整项评分标准；请限定具体条件或查阅该项全部原表子行。','SUBROW_CRITERION_NOT_GROUP_CRITERION')
    answer=meta['caption']+'：\n'+field+'：'+fields[field]+'\n['+card['citation_id']+']'
    return {**result,'answer_status':'SOURCE_EXTRACT','status_label':'原表字段摘录 · 待业务核对','answer':answer,
            'generation_mode':'NATIVE_TABLE_FIELD_NO_MODEL','native_table_field_audit':{'field':field,'page':meta['page'],'row':meta['row']},
            'notice':'按同一原表行摘录完整字段；空白不填0，标准分值不替代实际得分，未进行业务审核。'}
