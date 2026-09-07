# V2 INTERNAL TRIAL BASELINE

> 更新日期：2026-09-02。本文档描述 `rag-v1-refactor` 当前内部试用边界，不代表已具备生产切换条件。

## 状态

- TASK-020A ～ TASK-020H：CLOSED（Shadow/内部试用任务）
- V2_INTERNAL_TRIAL：TRIAL_READY
- PRODUCTION_READY：FALSE

## Git冻结点

- 分支：`rag-v1-refactor`
- HEAD：`0492754b7233b20a238710f296aad6b53d9661c5`
- HEAD说明：完善 V2 Shadow 检索问答与反馈闭环
- 工作区干净：False；源码无已跟踪修改，`data/`、`evaluation/`、`logs/`、`worker/` 为未跟踪运行/试验产物
- 冻结方式：`HEAD_RECORDED_NO_NEW_COMMIT_WORKTREE_DIRTY`
- 当前运行/评估产物不作为源码基线；如需提交，必须单独审查数据范围和脱敏状态。

## 冻结组件

- Document Intelligence Schema
- 020C Hierarchical Retrieval
- 020E Verified Evidence Bundle
- 020F Verified Answer Engine
- 020G Knowledge Growth Loop
- 8010 Trial Configuration

## 8010配置

- Host / Port：127.0.0.1:8010
- V2开关：True；仅8010：True
- 8000正式端口：8000；正式切换：False
- Root-002总体治理：PENDING_APPROVAL；仅明确批准的单文件可进入内存 Shadow 叠加读取
- Root-003启用：False
- 自动知识回写：False
- Provider依赖的Claim生成：试用策略关闭；当前不以Provider结果作为验收依据

## 当前试用资产

- Business Gold：3题（TQ-001～TQ-003）
- Trial Questions：10题，仅观察，不作为准确率分母
- 反馈形成的候选：只进入 Shadow 回归和人工审核，不自动发布知识
- 正式知识库、正式 Qdrant、8000 服务：均未被试用链路写入

## 继续入口

1. 先完成来源闭环和未确认问题的业务确认；
2. 对已批准来源执行 Shadow 回归，确认引用位置和必备事实；
3. 累积足够业务验收后，再单独评估 V2 是否切换到正式 8000。

## 安全冻结

- 禁止切换8000、扩大Root审批、自动发布Growth Candidate。
- 机器可读文件指纹见 `evaluation/v2_internal_trial_baseline/baseline_fingerprint.json`。
