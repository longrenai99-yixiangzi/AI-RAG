# 私有固定包装配模板

这些通用实现对应受控本机固定包的入口、只读候选适配和状态恢复。公开仓库不提供真实封包manifest、知识来源、候选、向量或运行状态，因此不能从此目录直接启动真实知识库。

装配时将start_release.py和state_recovery.py放入私有包根目录，将release_adapter.py放入runtime目录；同时提供获准manifest、冻结来源及运行代码。明确设置RAG_EXPECTED_CANDIDATE_HASH、RAG_RELEASE_TARGET与RAG_EMBEDDING_MODEL_PATH。私有包清单必须绑定装配后的文件指纹。

截至2026-10-12，适配器支持项目/期间/原文查阅、任务书草稿、评估交接与方案比选准备，保留原件只读和导出范围校验。项目及方案主题映射需要私有配置，详见[装配步骤与合成示例](../../docs/PRIVATE_DATA_ASSEMBLY.md)。这份通用模板与既有私有V包不是相同字节，不能复用原包身份。

默认执行只读precheck；serve必须同时匹配具体授权的候选、包清单SHA、端口、目标和写入/恢复范围。不能用本模板绕过Owner对具体封包的决定。状态恢复只能操作已核对的部署目录内部路径，普通停启不调用恢复。
