"""Supplement existing recall with section titles and explicit query scope checks."""
from pathlib import Path
from app.bm25 import BM25Index
from app.domain import Chunk
from app.retrieval.query_planner_v1 import SPECIALTIES

STAGES={'PRELIMINARY':('初步设计','初设'),'CONSTRUCTION':('施工图',),'SCHEME':('方案阶段','方案设计'),'CONCEPT':('概念设计','概念方案')}


def stages(text):
    return {key for key,aliases in STAGES.items() if any(a in text for a in aliases)}


def section_scope(question,candidate):
    heading=candidate.get('heading_path') or ''
    requested=stages(question);actual=stages(heading)
    specialty_terms=set(SPECIALTIES)-{'BIM','EPC','机电'}
    requested_specialty={s for s in specialty_terms if s in question}
    actual_specialty={s for s in specialty_terms if s in heading}
    # Multiple requested phases/professions may be intentional comparisons; do not silently narrow them.
    phase='MISMATCH' if len(requested)==1 and actual and requested.isdisjoint(actual) else 'MATCH' if len(requested)==1 and actual==requested else 'UNKNOWN'
    specialty='MISMATCH' if len(requested_specialty)==1 and actual_specialty and requested_specialty.isdisjoint(actual_specialty) else 'MATCH' if len(requested_specialty)==1 and actual_specialty==requested_specialty else 'UNKNOWN'
    return {'design_stage':phase,'specialty':specialty}


def mark_scope(question,candidates):
    result=[]
    for c in candidates:
        scope=dict(c.get('scope',{}))
        for key,value in section_scope(question,c).items():
            if scope.get(key)!='MISMATCH' and (value!='UNKNOWN' or key not in scope):scope[key]=value
        result.append({**c,'scope':scope})
    return result


class SectionTitleIndex:
    def __init__(self,sections):
        self.sections={s['section_id']:s for s in sections}
        self.bm25=BM25Index(Path('UNSAVED_SECTION_TITLE_INDEX'))
        self.bm25.build([Chunk(s['section_id'],s['source_path'],i,s['source_path'],Path(s['source_path']).name,
                               s['heading_path']+'\n'+s['text'],s['heading_path'],s['location']) for i,s in enumerate(sections)])

    def search(self,question):
        items=[]
        for sid,score in self.bm25.search(question,limit=len(self.sections)):
            s=self.sections[sid];scope=section_scope(question,s)
            if 'MISMATCH' in scope.values():continue
            items.append({**s,'evidence_id':'section-'+sid,'document_id':s['source_path'],'source_id':s['source_path'],
                          'file_name':Path(s['source_path']).name,'role':'DIRECT','score':score,'scope':scope,
                          'display_location':s['heading_path'],'retrieval_origin':'SECTION_TITLE_BM25_DELTA'})
            if len(items)==8:break
        return items
