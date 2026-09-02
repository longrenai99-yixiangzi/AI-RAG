# Shadow 原子证据层构建报告

> 本报告验证 Markdown、XLSX、PDF、DOCX、PPTX 的 Shadow 原子证据；未接入正式 Retriever，未写入正式 Qdrant，未调用 LLM。

## 1. 构建结果

| 指标 | 结果 |
|---|---:|
| 知识源 | `D:\设计管理` |
| 处理文件数 | 498 |
| 原子证据记录数 | 29027 |
| location 完整记录 | 29027 |
| XLSX 精确单行记录 | 757 |
| LLM 调用 | False |
| 正式 Qdrant 写入 | False |

## 2. 文件类型和粒度

| 类型 | 文件数 |
|---|---:|
| `.docx` | 12 |
| `.md` | 423 |
| `.pdf` | 16 |
| `.pptx` | 37 |
| `.xlsx` | 10 |

| 原子粒度 | 记录数 |
|---|---:|
| `line` | 7863 |
| `page_line` | 6941 |
| `paragraph` | 169 |
| `row` | 757 |
| `slide_line` | 12753 |
| `table_row` | 544 |

## 3. 状态和异常

| 状态 | 文件数 |
|---|---:|
| `front_matter_error` | 1 |
| `needs_ocr` | 2 |
| `parsed` | 495 |

### 异常文件

- `D:\设计管理\templates\entity.md`：`front_matter_error`；YAML front matter error: while constructing a mapping
  in "<unicode string>", line 2, column 10:
    created: {{date}}
             ^
found unhashable key
  in "<unicode string>", line 2, column 11:
    created: {{date}}
              ^

## 4. 这次验证证明了什么

- Markdown 事实不再只能依赖多行 Chunk；每个非空行都有独立 `evidence_id` 和单行 location。
- XLSX 数据不再只能依赖整 Sheet Chunk；每个非空行保留 Sheet、行号、表头和单元格字段。
- PDF、DOCX、PPTX 证据保留页、段落/表格行、幻灯片和文本行位置；扫描 PDF 仍标记为 `needs_ocr`。
- 原子证据仍然只是 Shadow 数据层，尚未改变正式检索排序和回答链路。
- 原子记录存在不等于业务语义已经确认；字段含义、版本和权限仍需治理。

## 5. 下一步

1. 用真实业务问题回放原子证据层，确认目标句/目标行是否能被精确命中。
2. 继续细化 PDF 页内段落、DOCX 表格单元格和 PPTX 文本框位置。
3. 通过 Shadow A/B 验证后，才考虑接入新的 Retriever。
