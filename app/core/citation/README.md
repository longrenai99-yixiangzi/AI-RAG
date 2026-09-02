# app/core/citation

未来职责：

- 统一 Citation 和 Evidence 数据结构；
- 文件名、页码、幻灯片页号、Sheet、章节和原文片段定位；
- 来源标记生成与引用校验；
- 为 API、前端和自动评测提供一致的引用结果。

迁移来源主要是当前 `app/answer.py` 中的上下文和 Citation 校验逻辑。当前阶段不拆分现有函数。
