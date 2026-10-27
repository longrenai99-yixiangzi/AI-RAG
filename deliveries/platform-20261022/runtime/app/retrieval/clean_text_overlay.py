"""Bind cleaned text, keyword tokens and replacement vectors to the same original rows."""
import hashlib
import json
from pathlib import Path

import numpy as np

from app.bm25 import tokenize
from app.ingestion.pdf_text_recovery import clean_source_records


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def apply_text_cleanup(folder, candidate_hash, model_digest, records, corpus, vectors):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['base_candidate_hash'] != candidate_hash or manifest['embedding_model_digest'] != model_digest:
        raise ValueError('Text cleanup candidate/model mismatch')
    if set(manifest['artifact_sha256']) != {'records.json','vectors.npy'}:
        raise ValueError('Unexpected text cleanup artifacts')
    if any(sha(folder/name) != h for name,h in manifest['artifact_sha256'].items()):
        raise ValueError('Text cleanup artifact changed')
    from app.ingestion import pdf_text_recovery
    if sha(Path(pdf_text_recovery.__file__).with_suffix('.json')) != manifest['profile_sha256']:
        raise ValueError('Text cleanup profile changed')
    revisions = json.loads((folder/'records.json').read_text(encoding='utf-8'))
    matrix = np.load(folder/'vectors.npy', allow_pickle=False)
    if matrix.ndim != 2 or matrix.shape[1] != 1024 or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=.003):
        raise ValueError('Invalid text cleanup vectors')
    by_id = {r['evidence_id']:i for i,r in enumerate(records)}
    if len({r['evidence_id'] for r in revisions}) != len(revisions):
        raise ValueError('Duplicate text cleanup row')
    indices = []
    for revision in revisions:
        i = by_id.get(revision['evidence_id'])
        if i is None or any(records[i][k] != revision[k] for k in ('source_path','source_version')):
            raise ValueError('Text cleanup source binding mismatch')
        if hashlib.sha256(records[i]['text'].encode()).hexdigest() != revision['original_text_sha256']:
            raise ValueError('Text cleanup original text changed')
        indices.append(i)
    normalized = clean_source_records([records[i] for i in indices])
    used = []; excluded = {}
    for revision, record in zip(revisions, normalized, strict=True):
        if record['text'] != revision['text'] or record['text'] == records[by_id[revision['evidence_id']]]['text']:
            raise ValueError('Text cleanup differs from source-verified watermark removal')
        n = revision['vector_row']
        if record['text'].strip():
            if type(n) is not int or not 0 <= n < len(matrix):
                raise ValueError('Missing text cleanup vector')
            used.append(n)
        elif n is not None:
            raise ValueError('Watermark-only row must have no searchable vector')
        else:
            excluded[record['evidence_id']] = 'WATERMARK_ONLY_NO_BUSINESS_TEXT'
    if sorted(used) != list(range(len(matrix))):
        raise ValueError('Text cleanup vector row alignment mismatch')
    vectors = vectors.copy()
    for i, revision, record in zip(indices, revisions, normalized, strict=True):
        records[i].update(text=record['text'], text_cleanup=record['text_cleanup'])
        corpus[i] = tokenize(record['text'])
        if revision['vector_row'] is not None:
            vectors[i] = matrix[revision['vector_row']]
        else:
            vectors[i] = 0
    return vectors, excluded, {'manifest_sha256':sha(folder/'manifest.json'), 'changed_rows':len(revisions),
                                'reencoded_rows':len(matrix), 'watermark_only_rows':len(excluded),
                                'source_versions':len({r['source_version'] for r in revisions})}
