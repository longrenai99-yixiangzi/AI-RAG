# V2.6.2 跨候选兼容性报告

> 条件性诊断报告：使用已记录的真实问题做离线重放，不计入当前候选 Live Shadow，不构成 Release Gate 通过。

- 历史去重问题：`352`
- 当前候选哈希：`77eaf3eb59ce4deb679213db5f93a326f79e774da998506d29bc442c1bdd1d18`
- 当前状态：`CONDITIONAL_COMPATIBILITY_ONLY_NOT_RELEASE_GATE`
- 当前答案状态：`{'ANSWERED': 221, 'PARTIAL_ANSWER': 131}`
- 状态转移：`{'ANSWERED -> ANSWERED': 180, 'CONFLICTING_ANSWER -> ANSWERED': 4, 'PARTIAL_ANSWER -> ANSWERED': 15, 'PARTIAL_ANSWER -> PARTIAL_ANSWER': 123, 'RETRIEVAL_PREVIEW_BM25_ONLY -> ANSWERED': 22, 'RETRIEVAL_PREVIEW_BM25_ONLY -> PARTIAL_ANSWER': 8}`

## 结论

1. 该报告可用于比较候选版本的状态变化和发现回归候选；
2. 离线重放不能替代当前候选的 Live Shadow；
3. 不授权 8010 切换，不写入 8000；
4. 正式发布前仍需当前候选哈希下的真实 Live Shadow、Rollback Drill 和人工复核。
