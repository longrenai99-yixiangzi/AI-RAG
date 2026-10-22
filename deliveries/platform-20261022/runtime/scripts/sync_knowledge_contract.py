"""Export one reproducible browser snapshot from the vault's canonical definitions."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.knowledge_contract import KnowledgeContract


def build_snapshot(vault: Path) -> dict:
    contract = KnowledgeContract(vault)
    refs = {key: vault / contract.data[key] for key in ('taxonomy_ref', 'architecture_ref', 'catalog_ref')}
    taxonomy, architecture, catalog = [json.loads(refs[key].read_text(encoding='utf-8')) for key in refs]
    assert len(taxonomy['actions']) == 13 and len(architecture['product_lines']) == 13
    assert {n['id']: len(n['children']) for n in taxonomy['nodes'] if n['id'] in {'02','03','04','05'}} == {'02':3,'03':2,'04':6,'05':2}
    inputs = {str(p.relative_to(vault)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [contract.path, *refs.values()]}
    source_rows = list(catalog['records'])
    for folder in taxonomy.get('deferred_roots', []):
        source_rows.extend({'path': p.relative_to(vault).as_posix(), 'title': p.stem, 'extension': p.suffix.lower(), 'primary': None, 'related': [], 'subtopics': [], 'classification_review': '技术管理待整理'} for p in sorted((vault/folder).rglob('*')) if p.is_file() and not p.is_symlink())
    rows = []
    for r in source_rows:
        path = vault / r['path']
        eligible, reason = contract.decision(path)
        domain = 'technical' if r['path'].split('/')[0] in taxonomy.get('deferred_roots', []) else 'design'
        candidates = [p['id'] for p in architecture['product_lines'] if any(term.casefold() in (r['path']+' '+r['title']).casefold() for term in (p.get('search_terms') or [p.get('subtype') or p['name']]))]
        rows.append({'id': 'PATH-'+hashlib.sha256(r['path'].encode()).hexdigest()[:20], 'path':r['path'], 'absolute_path':str(path), 'title':r['title'], 'extension':r['extension'], 'primary':r.get('primary'), 'related':r.get('related',[]), 'subtopics':r.get('subtopics',[]), 'domain':domain, 'product_line_candidates':candidates, 'classification_review':r['classification_review'], 'layer':r.get('layer','技术管理待整理'), 'answer_eligible':eligible, 'eligibility_reason':reason})
    assert len({r['path'] for r in rows}) == len(rows)
    return {'schema_version':1, 'input_sha256':inputs, 'taxonomy':taxonomy['nodes'], 'subtopics':taxonomy['subtopics'], 'actions':taxonomy['actions'], 'architecture':architecture, 'records':rows, 'summary':{'records':len(rows), 'answer_eligible':sum(r['answer_eligible'] for r in rows), 'eligibility_reasons':dict(Counter(r['eligibility_reason'] for r in rows))}, 'boundary':contract.data['boundary']}


def main():
    snapshot = build_snapshot(Settings.load().vault_root)
    target = ROOT/'knowledge-ui/src/data/knowledge-contract.generated.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(',',':')), encoding='utf-8')
    temp.replace(target)
    print(json.dumps(snapshot['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
