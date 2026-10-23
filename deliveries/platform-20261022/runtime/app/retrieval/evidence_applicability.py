"""Necessary source-purpose checks; filenames do not establish policy validity."""
import re
import unicodedata
import hashlib

from app.retrieval.named_source_scope import named_titles,file_key,path_key


def source_kind(citation):
    name=unicodedata.normalize('NFKC',citation.get('display_file_name') or citation.get('file_name') or '')
    classification_name=unicodedata.normalize('NFKC',citation.get('file_name','')+'\n'+name)
    match=re.search(r'(?:EPC(?:设计管理)?经验总结|项目复盘|复盘总结)\(([^()]+)\)',classification_name)
    project=match[1].strip() if match else None
    if project or re.search(r'复盘|案例|经验总结',classification_name):kind='PROJECT_CASE'
    elif re.search(r'讲稿|课件|培训|授课',classification_name):kind='LECTURE'
    elif re.search(r'手册|制度|规程|实施细则|管理办法|模板|示范文本',classification_name):kind='POLICY_OR_TEMPLATE_TITLE'
    else:kind='UNVERIFIED_SOURCE_KIND'
    return {'name':name,'kind':kind,'project':project}


def enforce_applicability(question,result):
    if not question.strip():return result
    if result.get('answer_status') in {'PIPELINE_ERROR','REVIEW_CONFLICT','SOURCE_VERSION_UNCONFIRMED','TABLE_SCHEMA_UNVERIFIED'}:return result
    cards=[dict(c) for c in result.get('citations',[])]
    primary=[c for c in cards if c.get('answer_usage') in {'PRIMARY','UNCLASSIFIED',None}]
    if not primary and result.get('answer_status')=='SCOPE_CLARIFICATION_REQUIRED' and result.get('evidence_scope_audit'):return result
    titles=named_titles(question) or []
    question_hash=hashlib.sha256(question.encode()).hexdigest()
    scope=result.get('debug',{}).get('source_scope',{})
    if scope.get('status')=='NAMED_SOURCE_VERSION_MATCHED':
        for c in primary:
            for binding in scope.get('bindings',[]):
                if (any(file_key(t)==file_key(binding['title']) for t in titles) and c.get('source_path')
                        and path_key(c['source_path']) in {path_key(p) for p in binding['available_paths']}
                        and c.get('source_version')==binding['source_version']):
                    c['verified_source_selection']={'question_sha256':question_hash,'title':binding['title'],
                        'source_path':c['source_path'],'source_version':c['source_version']}
    def verified_selection(c):
        b=c.get('verified_source_selection',{})
        return bool(b and b.get('question_sha256')==question_hash and b.get('source_path')==c.get('source_path')
                    and b.get('source_version')==c.get('source_version') and any(file_key(t)==file_key(b.get('title','')) for t in titles))
    selected_names={source_kind(c)['name'] for c in primary if verified_selection(c)}
    sources=[source_kind(c) for c in primary]
    template=bool(re.search(r'模板|示范文本|统一格式|标准格式|规定格式|制度(?:要求|规定)|手册',question))
    contents=bool(re.search(r'(?:策划书|任务书|计划书|报告|清单|表格).*(?:包括|包含|内容|章节|目录|格式|哪[一二三四五六七八九十几\d]+[个项])',question))
    lecture=bool(re.search(r'讲稿|课件|培训|授课',question)) and not re.search(r'不(?:要|能|按|用|以).*?(?:讲稿|课件)|局.*(?:手册|制度)|正式模板|统一模板',question)
    specified=bool(primary) and all(any(file_key(t)==file_key(c.get('file_name','')) for t in titles) for c in primary)
    interpretation=lecture or specified and not template
    cases=[s for s in sources if s['kind']=='PROJECT_CASE']
    intent_question=question
    for title in titles:intent_question=intent_question.replace('《'+title+'》','')
    examples=bool(re.search(r'案例|经验|复盘|借鉴',intent_question)) and not re.search(r'不(?:要|能|按|用|以).*?(?:案例|经验|复盘)',intent_question)
    def project_excluded(source):
        p=source['project']
        return bool(p and re.search(r'(?:不是|不要(?:用|按)?|排除|不包括)\s*'+re.escape(re.sub(r'项目$','',p)),question))
    def project_selected(source):
        p=source['project']
        alias=re.sub(r'项目$','',p or '')
        return bool(p and (p in question or len(alias)>=4 and alias in question)
                    or source['name'] in selected_names or any(file_key(t)==file_key(source['name']) for t in titles))
    decision='ALLOW';message='';notice=''
    if (template and not interpretation or contents and not interpretation and not cases) and (not sources or any(s['kind']!='POLICY_OR_TEMPLATE_TITLE' for s in sources)):
        decision='FORMAL_BASIS_REQUIRED' if template else 'DOCUMENT_BASIS_REQUIRED'
        message=('本题需要指定手册、制度或正式模板的可用主证据。当前未取得相应依据，不能用讲稿概括或项目经验替代；这不表示整库没有该资料。'
                 if template else '请明确要查正式模板、某份讲稿的概括，还是某个项目的实际文件。当前引用不足以认定通用的文档内容或固定部分数量。')
    elif any(project_excluded(s) for s in cases) or any(not project_selected(s) for s in cases) and not examples:
        decision='PROJECT_SCOPE_REQUIRED'
        message='当前找到的是项目复盘经验，请先明确项目，或明确说明要查案例借鉴。不能将该项目的做法直接当作通用制度要求。'
    elif cases:
        labels=list(dict.fromkeys(s['project'] or s['name'] for s in cases))
        notice='以下仅为'+ '、'.join(labels)+'的案例做法，不作为其他项目的统一要求：\n'
    elif interpretation and (template or contents):
        notice='以下仅据所指定资料的表述作答，尚未核验为正式手册模板或统一制度要求：\n'
    elif (template or contents) and sources:
        notice='以下仅据本次引用版本的手册或模板内容作答，适用范围与现行效力仍需核对：\n'
    audit={'decision':decision,'request_kind':'TEMPLATE_OR_POLICY' if template else 'DOCUMENT_CONTENTS' if contents else 'CASE_EXAMPLES' if examples else 'LOOKUP',
           'sources':sources,'source_kind_is_title_based_not_validity_review':True}
    output={**result,'citations':cards,'evidence_scope_audit':audit}
    if message:
        for c in cards:c['answer_usage']='BACKGROUND'
        output.update(answer_status='SCOPE_CLARIFICATION_REQUIRED',status_label='需要明确依据或项目范围',answer=message,
                      claims=[],selected_units=[],answer_completeness='UNANSWERED',generation_mode='NO_GENERATION',applicability=message)
        output.pop('model_draft',None)
    elif notice:
        output['applicability']=notice.strip()
        if output.get('answer') and not output['answer'].startswith(notice):
            text=output['answer'].removeprefix('以下为所引项目复盘中的案例做法：\n')
            output['answer']=notice+text
    return output


def require_applicable(question,citations):
    if not question.strip():raise ValueError('问题不能为空，未建立模型请求。')
    checked=enforce_applicability(question,{'citations':citations})
    if checked['evidence_scope_audit']['decision']!='ALLOW':raise ValueError(checked['answer'])
