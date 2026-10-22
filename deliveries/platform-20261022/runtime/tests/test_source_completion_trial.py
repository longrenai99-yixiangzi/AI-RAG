import json

import pytest

from scripts.run_source_completion_trial import RowOffsets,checkpoint
import numpy as np
from types import SimpleNamespace
from scripts import run_source_completion_trial as trial


def test_row_offsets_preserve_native_unicode_rows_and_reject_stale_source(tmp_path):
    path=tmp_path/'rows.jsonl'
    values=[{'source_path':'甲.pdf','table_id':'t1','text':'原始行一'}, {'source_path':'乙.pdf','table_id':'t2','text':'另一个来源'}, {'source_path':'甲.pdf','table_id':'t1','text':'原始行二'}]
    path.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values),encoding='utf-8')
    store=RowOffsets(path,tmp_path/'offsets.sqlite3')
    assert store.for_candidates([{'source_path':'甲.pdf'}]) == [values[0],values[2]]
    assert store.for_candidates([{'source_path':'乙.pdf'},{'source_path':'甲.pdf'}]) == values
    assert store.for_candidates([{'source_path':'缺失.pdf'}]) == []
    store.db.close()
    reopened=RowOffsets(path,tmp_path/'offsets.sqlite3');reopened.db.close()
    path.write_text(path.read_text(encoding='utf-8')+'{}\n',encoding='utf-8')
    with pytest.raises(RuntimeError):RowOffsets(path,tmp_path/'offsets.sqlite3')


def test_embedding_checkpoint_recovers_last_committed_prefix_and_pins_model(tmp_path):
    p=tmp_path/'vectors'
    checkpoint(p,'input-a',[[1.,0.],[0.,1.]])
    assert checkpoint(p,'input-a')==[[1.,0.],[0.,1.]]
    np.save(p.with_suffix('.npy'),np.array([[1.,0.],[0.,1.],[.5,.5]]))
    assert len(checkpoint(p,'input-a'))==2
    with pytest.raises(RuntimeError):checkpoint(p,'input-b')


def test_model_digest_handles_configured_string_path_and_changes_with_weights(tmp_path,monkeypatch):
    for name in ['config.json','tokenizer.json','pytorch_model.bin']:(tmp_path/name).write_bytes(b'v1')
    monkeypatch.setattr(trial.Settings,'load',lambda:SimpleNamespace(embedding_model=str(tmp_path)))
    before=trial.model_digest();(tmp_path/'pytorch_model.bin').write_bytes(b'v2')
    assert trial.model_digest()!=before
