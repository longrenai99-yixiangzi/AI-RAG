from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "retrieval_ab"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "knowledge_os_v2_1.dense.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "NOT_RUN_RESOURCE_LIMIT", "reason": "本地 CPU 上单个 sentence-transformers BGE-M3 batch 约 221 秒，完整 2,226 batches 预计数天；为避免占满机器和伪造指标已中止。FlagEmbedding 入口另因 datasets 导入 MemoryError 不可用。", "embedding_vectors_written": False, "runtime_enabled": False, "next_action": "提供 GPU/专用离线向量化环境后，按同一 Semantic Chunk V2 retrieval_text 重新运行。"}
    (OUT / "dense_v2_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
