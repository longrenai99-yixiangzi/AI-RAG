# V2 INTERNAL TRIAL BASELINE

## 状态

- TASK-020A ～ TASK-020H：CLOSED
- V2_INTERNAL_TRIAL：TRIAL_READY
- PRODUCTION_READY：FALSE

## Git冻结点

- HEAD：`79fd358858ebade825a7f0a42def8bb90a1cf70b`
- HEAD说明：建立 V1 工程基线
- 工作区干净：False
- 冻结方式：`HEAD_RECORDED_NO_NEW_COMMIT_WORKTREE_DIRTY`
- 未创建新Git提交；当前工作区包含未提交V2工件，基线以HEAD + 文件指纹共同锁定。

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
- Root-002：PENDING_APPROVAL；Root-003启用：False
- 自动知识回写：False

## 安全冻结

- 禁止切换8000、扩大Root审批、自动发布Growth Candidate。
- 机器可读文件指纹见 `evaluation/v2_internal_trial_baseline/baseline_fingerprint.json`。
