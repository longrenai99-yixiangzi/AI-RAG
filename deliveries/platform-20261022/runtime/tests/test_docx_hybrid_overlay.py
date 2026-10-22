from types import SimpleNamespace
from evaluation.cross_source_browser_20261019.run_docx_hybrid_overlay import effective_indices


def test_duplicate_ids_do_not_overwrite_source_versions_or_admit_navigation(tmp_path):
    source=tmp_path/'资料.docx';log=tmp_path/'log.md'
    docs={'source':{'source_path':str(source),'source_version':'b'*64},'log':{'source_path':str(log),'source_version':'a'*64}}
    old={'evidence_id':'same-id','document_id':'source','source_path':str(source),'source_version':'a'*64}
    current={**old,'source_version':'b'*64}
    rows=[old,current,dict(current),{'evidence_id':'log','document_id':'log','source_path':str(log),'source_version':'a'*64}]
    contract=SimpleNamespace(decision=lambda p:(False,'navigation_only') if p==log else (True,'original_material_unverified_facts'))
    selected,excluded=effective_indices(rows,docs,contract)
    assert selected==[1]
    assert excluded=={'NOT_CATALOG_VERSION_OR_PATH':1,'DUPLICATE_SAME_VERSION':1,'NAVIGATION_OR_EXCLUDED':1}


def test_conflicting_catalog_hashes_fail_closed(tmp_path):
    p=tmp_path/'资料.docx';row={'evidence_id':'id','document_id':'d','source_path':str(p),'source_version':'a'*64}
    docs={'d':{'source_path':str(p),'source_version':'a'*64,'content_hash':'b'*64}}
    selected,excluded=effective_indices([row],docs,SimpleNamespace(decision=lambda p:(True,'original_material_unverified_facts')))
    assert not selected and excluded=={'UNKNOWN_CATALOG_VERSION':1}
