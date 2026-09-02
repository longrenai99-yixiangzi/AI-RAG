# V2 8010 TRIAL REPORT

## 结论：V2_INTERNAL_TRIAL = TRIAL_READY

- 8010仅本机受控试用；8000未改动。
- B模式使用020C层级检索、020E核验、020F回答和020G候选检测。
- B模式优先使用本地BGE-M3 FP32；模型异常时只允许显式Sparse回退，不允许伪装为Dense成功。
- B平均总延迟：542.942ms。
- 安全门：{"unsupported_claim_rate": 0.0, "citation_coverage": 1.0, "citation_consistency": 1.0, "conflict_silent_resolution": 0, "lineage_unsafe_aggregation": 0, "gold_runtime_injection": 0, "automatic_knowledge_publish": 0, "unapproved_root_read": 0, "provider_http_requests": 0, "local_dense_runtime_verified": true}

30题为TRIAL_QUESTION，不作为Gold，也不向运行时注入已知答案。

## 反馈与人工审核验证

- Feedback Events：1
- Feedback Growth Proposals：1
- Review Decisions：1
- Automatic Knowledge Publish：0

## 最终安全门

- Formal Knowledge Base Write：0
- Formal Qdrant Write：0
- Root-002 Refresh / Root-003 Scan：0 / 0
- Provider HTTP Requests / Gold Runtime Injection：0 / 0
