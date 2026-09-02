# V2 INTERNAL TRIAL GUIDE

访问 `http://127.0.0.1:8010/v2-trial`。

1. 默认同时勾选 A（CURRENT / LEGACY）和 B（V2 VERIFIED），输入同一问题并比较结果。
2. 普通用户查看结论、回答状态和引用；管理员可展开B模式诊断。
3. 反馈只记录事件；“资料缺失”和“答案冲突”只形成待审核Proposal，不会发布知识。
4. 管理员可记录 APPROVE / REJECT / DEFER / MERGE；即使APPROVE也不会自动发布或改写索引。
5. 如需快速关闭V2，将 `V2_VERIFIED_RAG_ENABLED` 设为 `false` 并重启8010；8000不受影响。
