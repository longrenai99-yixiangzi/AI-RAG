# Document-level Retrieval Evaluation Report

> 本报告比较 TASK-014C Evidence Ranking 基线与 Document Profile Retrieval + Evidence Ranking。
> 不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。

## 1. Shadow 流程

Baseline：全库 Chunk Retrieval → Evidence Ranking。

New：Document Profile Retrieval → Candidate Documents → 文档内部 Chunk Retrieval → Evidence Ranking。

Document Profile Retrieval 仅使用 Profile 的 document_name、document_role、authority_level、scope、contains_topics 和相关限制字段；没有硬过滤，候选为空时保留回退空间。

## 2. 评估范围

- Gold Questions：100。
- Shadow Collection：4747 点；Shadow Chunk：4747。
- Document Profile：498 个；每题候选文档上限：30。
- Profile 候选 expected_file 覆盖率：44.00%。
- 平均候选文档数：30.00。
- LLM 调用次数：0。

## 3. 核心指标

| 指标 | TASK-014C Baseline | Document-level New |
|---|---:|---:|
| Expected File Hit Rate | 11.00% | 11.00% |
| Role Match Top-1 | 29.00% | 30.00% |
| Role Match Top-5 | 59.00% | 71.00% |
| Authority Match Top-1 | 29.00% | 30.00% |
| Authority Match Top-5 | 59.00% | 71.00% |
| Intent-Evidence Top-1 | 77.00% | 84.00% |
| Intent-Evidence Top-5 | 94.00% | 99.00% |
| 制度/案例/模板混淆率 | 10.00% | 6.00% |

## 4. 按 Intent 对比

| Intent | Baseline Expected File | New Expected File | Baseline Role Top-1 | New Role Top-1 | Baseline Intent Top-1 | New Intent Top-1 |
|---|---:|---:|---:|---:|---:|---:|
| CASE_QUERY | 33.33% | 40.00% | 33.33% | 33.33% | 100.00% | 100.00% |
| DISCIPLINE_QUERY | 6.67% | 6.67% | 16.67% | 20.00% | 100.00% | 96.67% |
| METHOD_QUERY | 8.70% | 4.35% | 13.04% | 17.39% | 43.48% | 60.87% |
| POLICY_QUERY | 5.26% | 10.53% | 36.84% | 31.58% | 63.16% | 73.68% |
| TEMPLATE_QUERY | 7.69% | 0.00% | 69.23% | 69.23% | 76.92% | 92.31% |

重点关注：POLICY_QUERY、TEMPLATE_QUERY、CASE_QUERY 的 Expected File Hit Rate 和 Role Match。

## 5. 结论与边界

1. Document Profile Retrieval 的价值应以 Expected File Hit Rate 为主要判断，不应只看角色匹配率。
2. 如果角色匹配提升但 Expected File Hit Rate 下降，说明 Profile 只改善了文档类别判断，没有解决具体文件主题和范围对齐。
3. 如果新流程出现候选文档为空，应回退到全库 Chunk Retrieval，不能造成零召回。
4. 本次新流程只在 Shadow 环境运行，未修改正式 Retriever，也未写入正式 Qdrant。

**TASK-014F：Document-level Retrieval Shadow Evaluation 完成。**
