import numpy as np
import pytest

from scripts.realign_v2_6_2_candidate_embeddings import align_embeddings


def test_reuses_vectors_by_unchanged_chunk_id_and_embeds_only_new_chunks():
    old_chunks = [
        {"chunk_id": "A", "raw_text": "A", "retrieval_text": "A"},
        {"chunk_id": "B", "raw_text": "B", "retrieval_text": "B"},
    ]
    old_vectors = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
    new_chunks = [old_chunks[1], {"chunk_id": "C", "raw_text": "C", "retrieval_text": "C"}, old_chunks[0]]

    aligned, reused, written = align_embeddings(old_chunks, old_vectors, new_chunks, lambda texts: [[3, 4] for _ in texts])

    assert reused == 2
    assert written == 1
    np.testing.assert_allclose(aligned, [[0, 1], [0.6, 0.8], [1, 0]])


def test_refuses_to_reuse_a_vector_when_chunk_content_changed():
    old_chunks = [{"chunk_id": "A", "raw_text": "old", "retrieval_text": "old"}]
    new_chunks = [{"chunk_id": "A", "raw_text": "new", "retrieval_text": "new"}]

    with pytest.raises(ValueError, match="REUSED_CHUNK_CONTENT_CHANGED"):
        align_embeddings(old_chunks, np.asarray([[1, 0]], dtype=np.float32), new_chunks, lambda _: [])
