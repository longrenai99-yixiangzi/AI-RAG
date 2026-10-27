"""Apply reviewed native prose expansions and hold unverified layout-only fragments."""
import hashlib
import json
from pathlib import Path

import numpy as np
from app.bm25 import tokenize
from app.ingestion.pdf_paragraph_context import complete_rows,prose_before_tables
from app.retrieval.clean_text_overlay import sha


def apply_paragraph_repair(folder,candidate_hash,model_digest,cleanup_hash,records,corpus,vectors):
    folder=Path(folder)
    read=lambda name:json.loads((folder/name).read_text(encoding='utf-8'))
    manifest=read('manifest.json')
    if (manifest['base_candidate_hash'],manifest['embedding_model_digest'],manifest['text_cleanup_manifest_sha256'])!=(candidate_hash,model_digest,cleanup_hash):
        raise ValueError('Paragraph repair candidate/model/cleanup differs')
    names={'paragraphs.json','safe_prose.json','rows.json','vectors.npy','exclusions.json'}
    if 'span_units.json' in manifest['artifact_sha256']:names.add('span_units.json')
    if set(manifest['artifact_sha256'])!=names or any(sha(folder/n)!=h for n,h in manifest['artifact_sha256'].items()):
        raise ValueError('Paragraph repair artifact changed')
    expected=complete_rows(records,read('paragraphs.json'));safe=prose_before_tables(records,read('safe_prose.json'))
    if set(expected)&set(safe):raise ValueError('Overlapping prose repair methods')
    expected.update(safe)
    span_specs=read('span_units.json') if 'span_units.json' in names else []
    if span_specs:
        from app.ingestion.pdf_source_spans import complete_spans
        spans=complete_spans(records,span_specs)
        if set(spans)&set(expected):raise ValueError('Source span repair overlaps earlier paragraphs')
        expected.update(spans)
    revisions=read('rows.json');excluded=read('exclusions.json');by_id={r['evidence_id']:i for i,r in enumerate(records)}
    if len({r['evidence_id'] for r in revisions})!=len(revisions) or set(expected)!={r['evidence_id'] for r in revisions}:
        raise ValueError('Paragraph repair row set mismatch')
    matrix=np.load(folder/'vectors.npy',allow_pickle=False)
    if matrix.shape!=(len(revisions),1024) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=.003):
        raise ValueError('Invalid paragraph repair vectors')
    for row in revisions:
        old=records[by_id[row['evidence_id']]]
        if row['text']!=expected[row['evidence_id']]['text'] or hashlib.sha256(old['text'].encode()).hexdigest()!=row['original_effective_text_sha256']:
            raise ValueError('Paragraph repair differs from native source or original effective row')
    if any(type(r['vector_row']) is not int for r in revisions) or sorted(r['vector_row'] for r in revisions)!=list(range(len(revisions))):
        raise ValueError('Paragraph vector row mismatch')
    holds={}
    versions={(r['source_path'],r['source_version']) for r in excluded}
    if any(sha(p)!=v for p,v in versions):raise ValueError('Layout exclusion original changed')
    for row in excluded:
        i=by_id.get(row['evidence_id']);old=records[i] if i is not None else None
        if (not old or any(row[k]!=old[k] for k in ('source_path','source_version'))
                or old.get('location',{}).get('section')!=f'Page {row["page"]}'
                or row['reason'] not in {'HELD_TABLE_CELL_SPLIT','HELD_TABLE_FIELD_BOUNDARY','HELD_FLOW_LAYOUT'}):
            raise ValueError('Invalid layout exclusion binding')
        if row['evidence_id'] in expected or row['evidence_id'] in holds:raise ValueError('Overlapping/duplicate layout exclusion')
        holds[row['evidence_id']]=row['reason']
    vectors=vectors.copy()
    for row in revisions:
        i=by_id[row['evidence_id']];record=expected[row['evidence_id']]
        records[i].update({k:record[k] for k in ('text','paragraph_completion','location','display_location') if k in record})
        corpus[i]=tokenize(record['text']);vectors[i]=matrix[row['vector_row']]
    return vectors,holds,{'manifest_sha256':sha(folder/'manifest.json'),'completed_boundaries':len(read('paragraphs.json'))+len(span_specs),'source_span_units':len(span_specs),
                         'reencoded_rows':len(revisions),'preserved_prose_rows':len(read('safe_prose.json')),'layout_rows_held':len(holds)}
