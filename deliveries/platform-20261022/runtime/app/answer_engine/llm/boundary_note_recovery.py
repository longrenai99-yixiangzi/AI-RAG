"""Quarantine one invalid notes field; never treat the original response as valid."""
from copy import deepcopy
import json
import re
from .response_schema import validate_response
from .citation_renderer import render_claim_citations
from .claim_validator import validate_claims,check_source_units


def recover_body(raw_response,policy,evidence):
    try:payload=json.loads(raw_response)
    except (TypeError,ValueError):return None
    allowed={item.source_id for item in evidence.items}
    initial=validate_response(payload,policy,allowed)
    if initial.valid or initial.errors!=['section_map references unknown claim_id']:return None
    notes=payload.get('section_map',{}).get('evidence_boundary')
    if not isinstance(notes,list) or not notes:return None
    # Atomic IDs are unresolved references, not natural-language notes to quarantine.
    if any(not isinstance(n,str) or not n.strip() or re.fullmatch(r'[A-Za-z_][\w.-]*',n.strip()) for n in notes):return None
    claims=payload.get('claims',[])
    if not claims or payload.get('evidence_insufficient'):return None
    if any(set(c)!={'claim_id','claim_text','evidence_ids'} or not re.fullmatch(r'C[1-9]\d*',c['claim_id']) for c in claims):return None
    candidate=deepcopy(payload);candidate['section_map']['evidence_boundary']=[]
    if not validate_response(candidate,policy,allowed).valid:return None
    rendered=render_claim_citations(candidate,policy,evidence)
    validation=validate_claims(rendered.answer_text,candidate['claims'],evidence)
    if not rendered.valid or not validation.valid:return None
    return {'payload':candidate,'validation':validation,'unverified_notes':list(notes),
            'original_schema_errors':initial.errors,'original_protocol_passed':False}


def project_partial_body(raw_response,policy,evidence):
    """Retain extractive claims with unresolved gaps; never report a complete answer."""
    try:payload=json.loads(raw_response)
    except (TypeError,ValueError):return None
    allowed={item.source_id for item in evidence.items}
    initial=validate_response(payload,policy,allowed)
    if not initial.valid and initial.errors!=['section_map references unknown claim_id']:return None
    gaps=payload.get('evidence_insufficient');claims=payload.get('claims')
    if not isinstance(gaps,list) or not gaps or not all(isinstance(g,str) and g.strip() for g in gaps):return None
    if not claims or any(set(c)!={'claim_id','claim_text','evidence_ids'} or not re.fullmatch(r'C[1-9]\d*',c['claim_id']) for c in claims):return None
    candidate=deepcopy(payload);notes=[]
    if not initial.valid:
        notes=candidate['section_map'].get('evidence_boundary')
        if not isinstance(notes,list) or not notes or any(not isinstance(n,str) or not n.strip() or re.fullmatch(r'[A-Za-z_][\w.-]*',n.strip()) for n in notes):return None
        candidate['section_map']['evidence_boundary']=[]
    if not validate_response(candidate,policy,allowed).valid:return None
    rendered=render_claim_citations(candidate,policy,evidence)
    validation=validate_claims(rendered.answer_text,claims,evidence)
    if not rendered.valid or not validation.valid:return None
    # shortcut: exact consecutive source clauses only; paraphrases need independent grounding.
    if not check_source_units(claims,evidence)['valid']:return None
    return {'payload':candidate,'validation':validation,'unverified_notes':list(notes),'unresolved_aspects':list(gaps),
            'original_schema_errors':initial.errors,'original_protocol_passed':initial.valid,
            'support_check':'EXACT_CONTIGUOUS_SOURCE_CLAUSES_NOT_SEMANTIC_OR_BUSINESS_VERIFICATION'}
