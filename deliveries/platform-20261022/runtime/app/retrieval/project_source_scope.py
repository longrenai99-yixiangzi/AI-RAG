"""Route an explicit project identifier from a case filename through existing version guards."""
import re
import unicodedata
from app.retrieval.named_source_scope import resolve_named_scope


def route_project_question(question,documents):
    if '《' in question:return {'status':'EXPLICIT_FILE_SELECTOR','question':question}
    names={}
    for doc in documents.values():
        filename=doc.get('file_name','');normalized=unicodedata.normalize('NFKC',filename)
        match=re.search(r'EPC设计管理经验总结\(([^()]+)\)',normalized)
        if not match:continue
        alias=re.sub(r'项目$','',match[1]).strip()
        if len(alias)>=4 and alias in question:names.setdefault(alias,set()).add(filename)
    if not names:return {'status':'NO_VERIFIED_FILENAME_SELECTOR','question':question}
    if len(names)!=1 or len(next(iter(names.values())))!=1:
        return {'status':'AMBIGUOUS_PROJECT_SELECTOR','question':question,'allowed_paths':[]}
    alias,files=next(iter(names.items()));filename=next(iter(files))
    selector='《'+filename+'》';scope=resolve_named_scope(selector,documents)
    if scope['status']!='NAMED_SOURCE_VERSION_MATCHED':return {**scope,'question':question}
    task=question.replace(alias+'项目','').replace(alias,'').lstrip('的，,：: ')
    return {'status':'PROJECT_FILENAME_VERSION_MATCHED','question':selector+'中，'+task,'original_question':question,'alias':alias,'source_scope':scope,'basis':'EXACT_CASE_FILENAME_ALIAS_AND_CURRENT_SOURCE_HASH_NOT_BUSINESS_FACT_VERIFICATION'}
