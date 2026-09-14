import sys
import threading
import time
import types

from app.retrieval.dense_provider import BGEM3DenseProvider


def test_concurrent_load_constructs_one_model(tmp_path, monkeypatch) -> None:
    calls = []

    class FakeModel:
        def __init__(self, *_args, **_kwargs) -> None:
            calls.append(1)
            time.sleep(0.03)

    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=FakeModel))
    provider = BGEM3DenseProvider(tmp_path, collection_name="dense-provider-lock-test")
    threads = [threading.Thread(target=provider.load) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
