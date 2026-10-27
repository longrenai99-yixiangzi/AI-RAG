"""Inspect inline link boundaries without guessing missing filenames or extensions."""
import re
from urllib.parse import unquote


def inline_links(text):
    result=[];end=0
    for match in re.finditer(r'!?\[([^\]\n]*)\]\(',text):
        if match.start()<end:continue
        start=match.end();i=start;depth=1
        if text[start:start+1]=='<':
            closing=text.find('>',start+1)
            if closing!=-1 and '\n' not in text[start:closing]:
                following=closing+1
                while following<len(text) and text[following] in ' \t':following+=1
                complete=text[following:following+1]==')'
                end=following+1 if complete else closing+1
                result.append({'label':match[1],'target':text[start+1:closing],'start':match.start(),'end':end,'complete':complete});continue
        while i<len(text) and text[i] not in '\r\n':
            if text[i]=='\\' and text[i+1:i+2] in {'(',')'}:i+=2;continue
            if text[i]=='(':depth+=1
            elif text[i]==')':
                depth-=1
                if depth==0:break
            i+=1
        complete=depth==0;end=i+1 if complete else i
        target=text[start:i].strip()
        target=target.replace(r'\(','(').replace(r'\)',')')
        result.append({'label':match[1],'target':target,'start':match.start(),'end':end,'complete':complete})
    return result


def primary_source_link(text):
    candidates=[]
    for link in inline_links(text):
        begin=text.rfind('\n',0,link['start'])+1
        stop=text.find('\n',link['end']);stop=len(text) if stop==-1 else stop
        before=text[begin:link['start']].strip();after=text[link['end']:stop].strip()
        if not after and (not before or re.fullmatch(r'\*\*来源\*\*\s*[:：]',before)):
            candidates.append(link)
    offset=0
    for line in text.splitlines(keepends=True):
        match=re.fullmatch(r'\s*(?:\*\*来源\*\*\s*[:：]\s*)?\[(?P<label>[^\]\n]+)\]\((?P<target>[^\r\n]+)\)\s*',line)
        if match:
            target=match['target'].strip();literal=unquote(target).replace('\\','/').rsplit('/',1)[-1]
            start=offset+match.start('label')-1;end=offset+len(line.rstrip('\r\n'))
            if (match['label']==literal and re.search(r'\.(?:pdf|docx|xlsx|pptx|doc|wps|txt|md|docm)$',literal,re.I)
                    and not any(c['start']==start for c in candidates)):
                candidates.append({'label':match['label'],'target':target,'start':start,'end':end,'complete':True,'syntax_mode':'LEGACY_FULL_FILENAME_LITERAL'})
        offset+=len(line)
    return candidates[0] if len(candidates)==1 else None
