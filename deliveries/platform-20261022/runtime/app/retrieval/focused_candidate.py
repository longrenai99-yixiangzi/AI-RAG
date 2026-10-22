"""Bound local reranking; keep full source text separate from ranking probes."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import re

from app.bm25 import tokenize
from app.retrieval.anchored_sections import expand_candidates
from app.retrieval.section_scope import mark_scope
from app.retrieval.named_source_scope import resolve_named_scope,path_key,ranking_question


def compound_coverage(question,text):
    units=[q.strip() for q in re.split(r'[？?；;]+',question) if q.strip()]
    if len(units)<2:return {'status':'NOT_COMPOUND','units':[]}
    filler={'什么','哪些','多少','几个','为何','请问','这个','那个','是否','如何','怎么','以及','分别'}
    checks=[]
    for unit in units:
        anchors=list(dict.fromkeys(t for t in tokenize(unit) if t not in filler and (len(t)>1 or t.isalnum() and t.isascii())))
        missing=[t for t in anchors if t not in text.casefold()]
        reasoning=bool(re.search(r'为什么|为何|如何|怎么|是否|原因|比较|区别|对比',unit))
        checks.append({'question':unit,'anchors':anchors,'missing_anchors':missing,'matched':bool(anchors) and not missing and not reasoning})
    # shortcut: lexical single-unit lookup only; reasoning and semantic coverage still need review.
    return {'status':'SINGLE_UNIT_ANCHORS_MATCHED' if all(c['matched'] for c in checks) else 'COMPOUND_COVERAGE_UNVERIFIED','units':checks}


class FocusedCandidate:
    """One existing provider per caller; bounded score cache, never cached answers."""
    def __init__(self,sections,title_index,reranker,documents=None):
        self.sections=sections;self.title_index=title_index;self.reranker=reranker
        self.documents=documents
        self.cache=OrderedDict();self.stats={'computed_pairs':0,'cache_hits':0}

    def rank(self,question,candidates):
        source_scope=resolve_named_scope(question,self.documents)
        allowed=source_scope['allowed_paths']
        if allowed is not None:
            if not allowed:return {'candidate_evidence':[],'bundle_status':source_scope['status'],'source_scope':source_scope}
            candidates=[c for c in candidates if path_key(c.get('source_path','')) in allowed]
        rows=expand_candidates(candidates,self.sections)
        unique=[];seen=set()
        for c in rows:
            identity=(path_key(c['source_path']),c.get('source_version'),c.get('heading_path'),c['text'])
            if identity not in seen:seen.add(identity);unique.append(c)
        rows=unique
        by_path={c['source_path']:c for c in rows};by_id={c['evidence_id']:deepcopy(c) for c in rows}
        title_hits=self.title_index.search(question)
        if allowed is not None:title_hits=[c for c in title_hits if path_key(c.get('source_path','')) in allowed]
        for c in title_hits:
            parent=by_path.get(c['source_path'])
            if parent:c.update(document_id=parent['document_id'],source_id=parent.get('source_id'))
            by_id.setdefault(c['evidence_id'],c)
        # Fuse ranks, not incomparable sparse/dense/section score scales.
        fusion={}
        for group in (rows,title_hits):
            for i,c in enumerate(group,1):fusion[c['evidence_id']]=fusion.get(c['evidence_id'],0)+1/(60+i)
        marked=mark_scope(question,list(by_id.values()))
        eligible=[c for c in marked if not any(v=='MISMATCH' for v in c['scope'].values())]
        eligible.sort(key=lambda c:(-fusion[c['evidence_id']],c['evidence_id']))
        chosen=eligible[:12]
        if not chosen:return {'candidate_evidence':[],'bundle_status':'SOURCE_SCOPE_MISSING'}
        task_question=ranking_question(question,self.documents)
        self.reranker.load();tok=self.reranker.model.tokenizer;probes=[];keys=[];pending=[];max_tokens=0
        for c in chosen:
            text=(c.get('heading_path') or '')+'\n'+c['text']
            offsets=tok(text,add_special_tokens=False,return_offsets_mapping=True)['offset_mapping']
            parts=[text[g[0][0]:g[-1][1]] for n in range(0,len(offsets),256) if (g:=offsets[n:n+256])]
            if not parts:raise ValueError('Empty ranking candidate')
            # Rank only a representative window; full candidate remains intact for evidence selection.
            qterms=set(tokenize(task_question));probe=max(parts,key=lambda part:len(qterms.intersection(tokenize(part))))
            size=len(tok.encode(task_question,add_special_tokens=False))+len(tok.encode(probe,add_special_tokens=False))+tok.num_special_tokens_to_add(pair=True)
            if size>self.reranker.max_length:raise ValueError('Ranking pair exceeds explicit token budget')
            max_tokens=max(max_tokens,size)
            key=hashlib.sha256(json.dumps([question,c.get('source_version'),text,probe],ensure_ascii=False).encode()).hexdigest()
            keys.append(key)
            c['ranking_probe']={'text':probe,'full_text_chars':len(c['text']),'probe_pair_tokens':size,'not_complete_coverage':len(parts)>1}
            if key in self.cache:self.stats['cache_hits']+=1;self.cache.move_to_end(key)
            else:probes.append(probe);pending.append(key)
        if probes:
            scores=self.reranker.score(task_question,probes)
            if scores is None or len(scores)!=len(pending) or not all(math.isfinite(v) for v in scores):raise ValueError('Invalid reranker response')
            for key,score in zip(pending,scores,strict=True):self.cache[key]=float(score)
            self.stats['computed_pairs']+=len(probes)
        for c,key in zip(chosen,keys,strict=True):c['reranker_score']=self.cache[key]
        while len(self.cache)>128:self.cache.popitem(last=False)
        chosen.sort(key=lambda c:(-c['reranker_score'],c['evidence_id']))
        # COUNT/LIST/"方案" are weak intent hints, not proof that several sources are required.
        coverage=compound_coverage(task_question,chosen[0]['text'])
        broad=bool(re.search(r'全流程|全部资料|跨专业|跨项目|综合汇总',question) or len(source_scope.get('bindings',[]))>1)
        temporal=bool(re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)|今年|去年|截至',task_question)) and chosen[0]['scope'].get('year')!='MATCH'
        comparison=bool(re.search(r'比较|对比|区别|异同|差异|发生.{0,4}变化',task_question))
        blocked=broad or temporal or comparison or coverage['status']=='COMPOUND_COVERAGE_UNVERIFIED'
        for i,c in enumerate(chosen):c['answer_usage']='PRIMARY' if i==0 and not blocked else 'BACKGROUND'
        return {'candidate_evidence':chosen,'bundle_status':'SOURCE_SCOPE_MISSING' if blocked else 'PRIMARY_SECTION_CANDIDATE',
                'source_scope':source_scope,
                'coverage_audit':coverage,
                'selection_notes':['所问年度或截止时间尚无明确范围证据，不能将通用原文直接认定为该时期的规定或变化。'] if temporal else ['本题需要比较或变化分析，单个主证据的排序结果不能证明比较完整。'] if comparison else ['本题要求跨资料或整体汇总，尚未验证完整覆盖。'] if broad else ['同一主证据尚未覆盖每个子问题的主题词，或包含尚未验证的推理问题。'] if blocked else ['仅使用一份主证据；多问句主题词匹配不等于业务答案完整性已验收。'],
                'ranking_audit':{'union_candidates':len(marked),'scope_eligible':len(eligible),'ranked_candidates':len(chosen),'max_pair_tokens':max_tokens,'candidate_limit':12,'probe_token_limit':256,'coverage_not_proven':True}}
