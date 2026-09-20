"""最小对照实验：定位 BGE-M3 CPU encode 段错误的触发条件。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODE = sys.argv[1] if len(sys.argv) > 1 else "A"
BGE_PATH = ROOT / "models" / "bge-m3"

TEXTS = ["中建三局二公司设计管理价值创造点清单", "EPC 项目设计管理四季度检查通报", "限额设计与比选落实情况"] * 3

print(f"[probe] MODE={MODE}", flush=True)

client = None
if MODE in {"B", "C"}:
    from qdrant_client import QdrantClient

    qdir = ROOT / "data" / "shadow" / "full_corpus_qdrant_expanded"
    client = QdrantClient(path=str(qdir))
    print(f"[probe] qdrant opened: {qdir}", flush=True)

if MODE == "C":
    from qdrant_client import QdrantClient as _QC

    _QC(location=":memory:")
    print("[probe] in-memory qdrant opened", flush=True)

from FlagEmbedding import BGEM3FlagModel  # noqa: E402

started = time.perf_counter()
model = BGEM3FlagModel(str(BGE_PATH), use_fp16=False)
print(f"[probe] model loaded in {time.perf_counter() - started:.1f}s", flush=True)

for batch in (4, 8):
    started = time.perf_counter()
    result = model.encode(TEXTS[:batch], batch_size=batch, max_length=1024, return_dense=True, return_sparse=False, return_colbert_vecs=False)
    vecs = result["dense_vecs"]
    print(f"[probe] encode batch={batch} ok shape={vecs.shape} elapsed={time.perf_counter() - started:.2f}s", flush=True)

print("[probe] PASS", flush=True)
