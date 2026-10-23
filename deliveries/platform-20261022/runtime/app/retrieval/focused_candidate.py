"""Bound local reranking; keep full source text separate from ranking probes."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import re
import unicodedata

from app.bm25 import tokenize
from app.retrieval.anchored_sections import expand_candidates,ANCHOR
from app.retrieval.section_scope import mark_scope
from app.retrieval.named_source_scope import resolve_named_scope,path_key,ranking_question
from app.retrieval.section_overview import comparison_required,collect_overview,topic_key
from app.retrieval.section_tables import parallel_facets,associate_section


def explicit_topic_coverage(question,candidate):
    if candidate.get('explanation_block') and re.search(r'表头|字段|列名|单元格',question):
        return {'status':'RELATED_MENTION_ONLY','reason':'NUMBERED_NOTE_IS_NOT_TABLE_FIELDS'}
    match=re.match(r'^([^，,。；;！？?《》]{2,50}?)(?:实施前|应当|应该|应(?:重点|主要)?(?:完成|关注|具备|满足|采取|包含|包括|遵循|考虑|明确)|需要|如何|怎么|有哪些(?:具体)?(?:要求|做法|内容|措施|规定))',question)
    if not match:return {'status':'NOT_EXPLICIT_TOPIC'}
    topic=re.sub(r'^(?:请问|请说明|请|关于|针对)+','',match[1]).strip()
    key=topic_key(topic).replace('设计供方','设计方').replace('的','')
    if key.startswith('设计管理') and len(key[4:])>=4:key=key[4:]
    if len(key)<2 or key in {'设计','管理','工作','项目','本项目','该项目','设计管理'}:return {'status':'NOT_EXPLICIT_TOPIC'}
    text=unicodedata.normalize('NFKC',(candidate.get('heading_path') or '')+'\n'+candidate['text'])
    text=re.sub(r'[ \t\u3000]+','',text).replace('管控','管理').replace('设计供方','设计方').replace('的','')
    status='TOPIC_PRESENT' if key in text else 'TOPIC_NOT_FOUND'
    heading=topic_key(candidate.get('heading_path') or '').replace('设计供方','设计方').replace('的','')
    asks_contents=bool(re.search(r'(?:哪些|什么|哪几项)(?:主要)?内容|内容(?:是|有|包括)',question))
    # shortcut: content-list lookups need a topic heading or explicit subject statement; mentions alone cannot prove a list.
    if status=='TOPIC_PRESENT' and asks_contents and key not in heading:
        statement=re.escape(key)+r'(?:主要|应当|应该|需要|应|需|的)*(?:包括|包含|涵盖|明确|考虑|关注|由|内容为|内容是|内容有|内容[：:]|[：:])'
        if not re.search(statement,text):status='RELATED_MENTION_ONLY'
    return {'status':status,'requested_topic':topic,'normalized_topic':key}


def compound_coverage(question,text):
    units=[q.strip() for q in re.split(r'[？?；;]+',question) if q.strip()]
    if len(units)<2:return {'status':'NOT_COMPOUND','units':[]}
    filler={'什么','哪些','多少','几个','为何','请问','这个','那个','是否','如何','怎么','以及','分别'}
    checks=[]
    for unit in units:
        anchors=list(dict.fromkeys(t for t in tokenize(unit) if t not in filler and (len(t)>1 or t.isalnum() and t.isascii())))
        missing=[t for t in anchors if t not in text.casefold()]
        reasoning=bool(re.search(r'为什么|为何|如何|怎么|是否|原因',unit)) or comparison_required(unit)
        checks.append({'question':unit,'anchors':anchors,'missing_anchors':missing,'matched':bool(anchors) and not missing and not reasoning})
    # shortcut: lexical single-unit lookup only; reasoning and semantic coverage still need review.
    return {'status':'SINGLE_UNIT_ANCHORS_MATCHED' if all(c['matched'] for c in checks) else 'COMPOUND_COVERAGE_UNVERIFIED','units':checks}


class FocusedCandidate:
    """One existing provider per caller; bounded score cache, never cached answers."""
    def __init__(self,sections,title_index,reranker,documents=None,records=()):
        self.sections=sections;self.title_index=title_index;self.reranker=reranker
        self.documents=documents
        self.records_by_source={}
        for r in records:
            self.records_by_source.setdefault((path_key(r['source_path']),r['source_version']),[]).append(r)
        by_source={}
        for s in sections:
            if len(s.get('paragraph_anchors',[]))>1:
                by_source.setdefault((path_key(s['source_path']),s['source_version']),[]).append(s)
        for key,group in by_source.items():
            rows=self.records_by_source.get(key,[])
            if not rows:continue
            anchors={a for r in rows for a in ANCHOR.findall(r['text'])}
            self.records_by_source[key]=[{**rows[0],**s,'evidence_id':'section-'+s['section_id'],
                'text':s['text'] if set(s['paragraph_anchors'][1:]).issubset(anchors) else ''} for s in group]
        self.cache=OrderedDict();self.stats={'computed_pairs':0,'cache_hits':0}

    def rank(self,question,candidates,*,allowed_versions=None):
        source_scope=resolve_named_scope(question,self.documents)
        allowed=source_scope['allowed_paths']
        if allowed is not None:
            if not allowed:return {'candidate_evidence':[],'bundle_status':source_scope['status'],'source_scope':source_scope}
            candidates=[c for c in candidates if path_key(c.get('source_path','')) in allowed]
        if allowed_versions is not None:
            candidates=[c for c in candidates if (path_key(c['source_path']),c['source_version']) in allowed_versions]
        rows=expand_candidates(candidates,self.sections)
        unique=[];seen=set()
        for c in rows:
            identity=(path_key(c['source_path']),c.get('source_version'),c.get('heading_path'),c['text'])
            if identity not in seen:seen.add(identity);unique.append(c)
        rows=unique
        by_path={c['source_path']:c for c in rows};by_id={c['evidence_id']:deepcopy(c) for c in rows}
        title_hits=self.title_index.search(question,allowed_versions=allowed_versions) if allowed_versions is not None else self.title_index.search(question)
        if allowed_versions is not None:title_hits=[c for c in title_hits if (path_key(c['source_path']),c['source_version']) in allowed_versions]
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
        for c in chosen:c['topic_coverage']=explicit_topic_coverage(task_question,c)
        topical=[c for c in chosen if c['topic_coverage']['status'] not in {'TOPIC_NOT_FOUND','RELATED_MENTION_ONLY'}]
        topic_blocked=not topical
        if topical:chosen=topical+[c for c in chosen if c['topic_coverage']['status'] in {'TOPIC_NOT_FOUND','RELATED_MENTION_ONLY'}]
        # COUNT/LIST/"方案" are weak intent hints, not proof that several sources are required.
        coverage=compound_coverage(task_question,chosen[0]['text'])
        broad=bool(re.search(r'全流程|全部资料|跨专业|跨项目|综合汇总',question) or len(source_scope.get('bindings',[]))>1)
        temporal=bool(re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)|今年|去年|截至',task_question)) and chosen[0]['scope'].get('year')!='MATCH'
        comparison=comparison_required(task_question)
        facets=parallel_facets(task_question)
        if facets:topic_blocked=False
        blocked=broad or temporal or comparison or topic_blocked or (coverage['status']=='COMPOUND_COVERAGE_UNVERIFIED' and not facets)
        for i,c in enumerate(chosen):c['answer_usage']='PRIMARY' if i==0 and not blocked else 'BACKGROUND'
        chapter={'status':'NOT_PARENT_OVERVIEW'}
        if not blocked:
            parent=chosen[0]
            siblings,chapter=collect_overview(task_question,parent,self.records_by_source.get((path_key(parent['source_path']),parent['source_version']),()))
            if siblings:
                for c in chosen:c['answer_usage']='BACKGROUND'
                ids={c['evidence_id'] for c in siblings}
                chosen=siblings+[c for c in chosen if c['evidence_id'] not in ids]
            elif chapter['status']=='PARENT_COVERAGE_UNVERIFIED':
                blocked=True
                for c in chosen:c['answer_usage']='BACKGROUND'
        table_audit={'status':'NOT_APPLICABLE'};facet_audit=None
        if not blocked and not re.search(r'多少|几人|人数|合计|统计|计算|占比|金额|费用|差额',task_question):
            seed=chosen[0]
            selected,table_audit,facet_audit=associate_section(task_question,seed,chosen,self.records_by_source.get((path_key(seed['source_path']),seed['source_version']),()))
            if selected is not None:
                for c in chosen:c['answer_usage']='BACKGROUND'
                ids={c['evidence_id'] for c in selected}
                chosen=selected+[c for c in chosen if c['evidence_id'] not in ids]
                blocked=not selected
            if facet_audit:facet_audit['question_sha256']=hashlib.sha256(question.encode()).hexdigest()
        if temporal:notes=['所问年度或截止时间尚无明确范围证据，不能将通用原文直接认定为该时期的规定或变化。']
        elif comparison:notes=['本题需要比较或变化分析，单个主证据的排序结果不能证明比较完整。']
        elif broad:notes=['本题要求跨资料或整体汇总，尚未验证完整覆盖。']
        elif topic_blocked:notes=['候选尚未明确涵盖所问主题，只提供相关线索，不用相似段落代答；不能据此认定原件或整库没有答案。']
        elif table_audit['status'] in {'TABLE_CONTEXT_LIMIT_EXCEEDED','EVIDENCE_CONTEXT_LIMIT_EXCEEDED','TOO_MANY_FACETS'}:notes=['子问数量或同节证据超过完整引用上限，未截断表格或据此计算，请缩小问题或查阅原表。']
        elif facet_audit and facet_audit['status']=='PARTIAL':notes=['并列子问只有部分取得明确线索，未定位的部分将单列缺口。']
        elif table_audit['status']=='NO_MATCHING_SECTION_ROW' and blocked:notes=['当前导语或候选不足以回答所问内容，未把“如下”或表头当作业务规则。']
        elif chapter['status']=='PARENT_COVERAGE_UNVERIFIED':notes=['父章节的子节说明尚未完整取得，或本题要求清单、统计及限定范围；未用单个子节代答。']
        elif blocked:notes=['同一主证据尚未覆盖每个子问题的主题词，或包含尚未验证的推理问题。']
        elif chapter['status']=='PARENT_NARRATIVES_COLLECTED':notes=['已汇聚同资料同版本的子节说明；附表未逐行核对，业务完整性仍待验收。']
        elif chapter['status']=='PARENT_FOCUS_EVIDENCE_COLLECTED':notes=['已按所问评价维度补取同章明确说明，尚未证明全部子问均已覆盖。']
        else:notes=['仅使用一份主证据；多问句主题词匹配不等于业务答案完整性已验收。']
        return {'candidate_evidence':chosen,'bundle_status':'SOURCE_SCOPE_MISSING' if blocked else 'PRIMARY_SECTION_CANDIDATE',
                'source_scope':source_scope,
                'topic_coverage':{'status':'PARALLEL_TOPICS_CHECKED_SEPARATELY'} if facets else explicit_topic_coverage(task_question,chosen[0]),
                'intent_audit':{'comparison_required':comparison},'chapter_coverage':chapter,
                'coverage_audit':coverage,
                'table_association_audit':table_audit,'facet_coverage':facet_audit,
                'selection_notes':notes,
                'ranking_audit':{'union_candidates':len(marked),'scope_eligible':len(eligible),'ranked_candidates':len(keys),'returned_candidates':len(chosen),'max_pair_tokens':max_tokens,'candidate_limit':12,'probe_token_limit':256,'coverage_not_proven':True}}
