"""Exact named-source/version scope, adapted from the existing structure trial."""
import hashlib
from pathlib import Path
import re
import unicodedata


def file_key(name,*,stem=True):
    name=unicodedata.normalize('NFKC',str(name)).replace('\\','/').casefold()
    if stem:name=re.sub(r'\.(?:pdf|pptx?|docx?|xlsx?|md|txt|wps)$','',name)
    if stem and '/' not in name and name.startswith('《') and name.endswith('》'):name=name[1:-1]
    return re.sub(r'\s+','',name)


def named_document_ids(documents,title):
    explicit=bool(re.search(r'\.(?:pdf|pptx?|docx?|xlsx?|md|txt|wps)$',title,re.I))
    key=file_key(title,stem=not explicit);field='source_path' if '/' in title or '\\' in title else 'file_name'
    if not key:return set()
    return {did for did,d in documents.items() if any(file_key(value,stem=not explicit)==key for value in [d.get(field,''),d.get('reference_note_path','') if field=='source_path' else ''])}


def path_key(path):return str(Path(path).resolve()).casefold()


def named_titles(question):
    """Read outer selectors even when a filename itself contains book-title brackets."""
    titles=[];depth=0;start=0
    for i,char in enumerate(question):
        if char=='《':
            if depth==0:start=i+1
            depth+=1
        elif char=='》':
            if depth==0:return None
            depth-=1
            if depth==0:titles.append(question[start:i])
    return None if depth or any(not title.strip() for title in titles) else list(dict.fromkeys(titles))


def ranking_question(question,documents):
    """Keep the original question for scope; omit verified selectors only from ranking."""
    result=question
    for title in named_titles(question) or []:
        if documents is not None and named_document_ids(documents,title):result=result.replace('《'+title+'》','')
    return re.sub(r'^[\s中，,:：]+','',result).strip() or question


def resolve_named_scope(question,documents):
    titles=named_titles(question)
    if titles is None:return {'status':'SOURCE_SCOPE_MISSING','allowed_paths':[],'reason':'Source selector brackets are incomplete'}
    if not titles:return {'status':'UNNAMED_QUERY','allowed_paths':None}
    if documents is None:return {'status':'SOURCE_SCOPE_MISSING','allowed_paths':[],'reason':'No trusted document catalog supplied'}
    allowed=set();bindings=[]
    for title in titles:
        matches=named_document_ids(documents,title)
        if not matches:return {'status':'SOURCE_SCOPE_MISSING','allowed_paths':[],'reason':'Named document is not in this candidate catalog','requested_title':title}
        versions={};unavailable=[]
        for did in matches:
            d=documents[did];hashes={str(d[k]) for k in ('source_version','source_hash','content_hash','sha256') if re.fullmatch(r'[a-fA-F0-9]{64}',str(d.get(k,'')))}
            if len(hashes)!=1:return {'status':'SOURCE_SCOPE_MISSING','allowed_paths':[],'reason':'Named source version is unknown or internally inconsistent'}
            version=next(iter(hashes)).lower();versions.setdefault(version,[]).append(d)
        if len(versions)!=1:return {'status':'CONFLICTING_EVIDENCE','allowed_paths':[],'reason':'More than one indexed version has this name','requested_title':title}
        version,docs=next(iter(versions.items()));valid=[]
        for d in docs:
            path=Path(d.get('source_path') or '')
            try:current=hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:current=None
            if current==version:valid.append(path_key(path))
            else:unavailable.append(str(path))
        if not valid:return {'status':'SOURCE_SCOPE_MISSING','allowed_paths':[],'reason':'Named source bytes no longer match the indexed version','requested_title':title}
        allowed.update(valid);bindings.append({'title':title,'source_version':version,'available_paths':valid,'unavailable_paths':unavailable})
    return {'status':'NAMED_SOURCE_VERSION_MATCHED','allowed_paths':sorted(allowed),'bindings':bindings}
