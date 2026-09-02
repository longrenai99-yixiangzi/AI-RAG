# TRIAL-CYCLE-01 初始基线

> 本阶段冻结 V2 核心架构，只建设真实业务验收资产与知识源闭环台账。不得把题目答案注入运行时，不扩大 Root，不自动发布知识。

## TRIAL-01A：Business Acceptance Registry

- 初始问题：13 题；Business Gold：3 题；Trial Questions：10 题。
- 没有凭空补齐30～50题；其余题目将由8010真实提问和Owner确认逐步进入。
- 10道历史BA保留来源确认记录，但因新Schema仍缺少部分机器可验关键事实，先放入Trial观察集，不虚报为完整新Gold。

## TRIAL-01B：Source Closure Register

- Source状态分布：`{'INDEXED_SHADOW': 5, 'PENDING_APPROVAL': 3, 'SOURCE_IDENTIFIED': 2, 'VERIFIED_RUNTIME': 3}`。
- `SOURCE_IDENTIFIED`：已知目标文件名，但尚待物理路径/治理确认。
- `PENDING_APPROVAL`：来源已知但当前运行时没有读取授权；等待审批，不重复扫描Root。
- `INDEXED_SHADOW` / `VERIFIED_RUNTIME`：可进入Shadow回归，不等于可写入正式知识库。

## 后续准入

1. Trial Question获得Owner确认的来源、位置和关键事实后，才升级为Business Gold。
2. 每次修复必须同时运行Business Gold与Trial Questions；Trial只观察趋势，不用于准确率宣传。
3. Source Closure状态未到`APPROVED_FOR_SHADOW`前，不导入外部正文。
