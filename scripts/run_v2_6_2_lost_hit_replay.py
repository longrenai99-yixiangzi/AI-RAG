from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
MODEL = ROOT / "models" / "bge-m3"
QUESTIONS = {
    "LSR-L02": "之寓·保税区人才公寓项目的限额设计中，为什么没有进行精装修指标对比？",
    "LSR-L04": "涟水第三水厂项目已入图策划金额约多少万元？创效率是多少？",
    "LSR-L06": "丰台崔村旧改项目通过调研沟通将 60 系列外窗变更为 65 系列并成功入图，重新认质认价后单项创效多少万元？",
    "LSR-L07": "泸州垃圾焚烧发电厂项目累计减亏多少万元？盈利多少万元？优化金额总计约多少、设计优化率多少？",
}


def main() -> int:
    engine = V25LiveShadow()
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_lost_hit_replay", use_fp16=False, batch_size=1)
    records = []
    try:
        for review_id, question in QUESTIONS.items():
            result = engine.run(question, {"answer_status": "ANSWERED", "citations": []}, query_vector=provider.embed_query(question))
            records.append({
                "review_id": review_id,
                "question": question,
                "candidate_status": result.get("v2_status"),
                "bundle_status": result.get("v2_bundle_status"),
                "answer": result.get("v2_answer"),
                "citations": result.get("v2_citations") or [],
                "candidate_hash": result.get("candidate_hash"),
                "rescues": result.get("owner_answer_gold_source_rescue"),
                "validation": result.get("validation"),
            })
    finally:
        provider.close()
    payload = {
        "schema_version": "knowledge_os_v2_6_2.lost_hit_replay",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "REPLAY_COMPLETE_NOT_RELEASE_GATE",
        "candidate_hash": engine.candidate_hash,
        "records": records,
    }
    path = V26 / "v2_6_2_lost_hit_replay.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "candidate_hash": engine.candidate_hash, "records": [{"review_id": r["review_id"], "status": r["candidate_status"], "bundle": r["bundle_status"]} for r in records]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
