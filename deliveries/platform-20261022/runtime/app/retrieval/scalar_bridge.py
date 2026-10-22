"""Connect the already validated scalar renderer to the shared candidate; no new index."""
import re
from app.ingestion.scalar_evidence import project_key, requested_metrics
from app.retrieval.named_source_scope import path_key
from app.retrieval.query_planner_v1 import plan_query
from app.trial.existing_text_answers import render_existing
from app.verified_answer_engine_v2 import validate


def matching_links(question, links):
    if (not requested_metrics(question) or not re.search(r'多少|几天|金额|费用|总投资',question)
            or re.search(r'原因|为什么|如何|比例|多少项|以及.*(?:谁|何时)',question)):
        return {}
    key = project_key(question)
    return {path: link for path, link in links.items()
            if any(project_key(a) and project_key(a) in key for a in link['scope']['aliases'])}


def scope_paths(links):
    return {path_key(p) for md, link in links.items() for p in (md, link['original_path'])}


def scalar_bundle(question, recalled, links):
    bundle = {'query_id': 'retrieved-scalar', 'question': question, 'query_plan': plan_query(question).to_dict(),
              'bundle_status': 'VERIFIED', 'candidate_evidence': recalled, 'verified_evidence': []}
    if any(bundle['query_plan'].get(k) for k in ('year','period','organization')):
        return {'candidate_evidence': [], 'bundle_status': 'SOURCE_SCOPE_MISSING',
                'selection_notes': ['现有数值范围未核验所问年份、期间或组织条件。']}
    rendered = render_existing(bundle, links, recalled_parents=recalled)
    if rendered is None:
        return {'candidate_evidence': [{**r, 'answer_usage': 'BACKGROUND'} for r in recalled[:8]],
                'bundle_status': 'SOURCE_SCOPE_MISSING',
                'selection_notes': ['当前同版证据尚未核验所问金额指标、单位或条件，不能把相关金额片段当作答案。']}
    answer, grounded = rendered
    validation = validate(answer, grounded)
    if not validation['valid']:
        raise ValueError('Scalar answer failed source-bound validation')
    direct = {eid for claim in answer['claims'] if claim['claim_type'] == 'DIRECT' for eid in claim['evidence_ids']}
    return {**grounded, 'scalar_answer': answer,
            'candidate_evidence': [{**r, 'role': 'DIRECT', 'answer_usage': 'PRIMARY' if r['evidence_id'] in direct else 'BACKGROUND'}
                                   for r in grounded['candidate_evidence']]}
