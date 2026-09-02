# Knowledge Source Root Policy

## TASK-016B-1.5：Knowledge Source Root Approval Design

## 1. 设计目标

本文件用于确定企业知识库允许扫描和读取的只读知识源范围，为后续多 Root Source Discovery、Document Pipeline 和 Shadow Index 提供边界。

本任务只完成 Root Policy 设计，不修改代码，不扫描新增 Root，不写入正式 Qdrant，也不自动发布知识。

## 2. TASK-016B-1 Source Discovery 当前统计

当前唯一正式扫描 Root：

```text
D:\设计管理
```

Source Discovery 结果：

| 指标 | 数量 |
|---|---:|
| Markdown 发现页 | 407 |
| SourceLink | 1784 |
| SourceRecord | 1703 |
| 已解析到存在路径的文件 | 1563 |
| 缺失文件 | 140 |
| BODY_AVAILABLE | 994 |
| REGISTERED_ONLY | 129 |
| NEEDS_REVIEW | 440 |
| LINK_BROKEN | 140 |

外部引用主要指向：

```text
D:\工作\二公司技术部
D:\工作\设计支持中心
```

Source Discovery 中的路径统计：

| 外部 Root | SourceRecord | 已存在 | NEEDS_REVIEW | LINK_BROKEN |
|---|---:|---:|---:|---:|
| `D:\工作\二公司技术部` | 314 | 225 | 225 | 89 |
| `D:\工作\设计支持中心` | 58 | 38 | 38 | 20 |

这些路径目前只能被识别为外部候选，不能直接进入正式知识库。

## 3. Knowledge Root 分级建议

### Root-001：当前正式知识源

| 属性 | 值 |
|---|---|
| `root_id` | `Root-001` |
| `path` | `D:\设计管理` |
| `owner` | 设计管理知识库维护方 |
| `purpose` | Wiki、概念页、实体页、Query 页、raw 登记页和已纳入知识库的企业资料 |
| `read_only` | `true` |
| `approval_status` | `APPROVED_ACTIVE` |

说明：

- 继续作为当前默认扫描 Root；
- 保持只读；
- 允许进入 Source Discovery、Document Pipeline 和 Shadow Index；
- 不代表其中所有文件都具有同等权威性；权威性仍由 Metadata/Governance 判断。

### Root-002：技术部外部资料 Root

| 属性 | 值 |
|---|---|
| `root_id` | `Root-002` |
| `path` | `D:\工作\二公司技术部` |
| `owner` | 二公司技术部/设计与技术管理责任部门 |
| `purpose` | 设计任务书、设计策划、方案比选、工作计划、项目复盘、技术资料和业务台账的原始文件来源 |
| `read_only` | `true` |
| `approval_status` | `PENDING_APPROVAL`

说明：

- 当前只能作为候选 Root 登记；
- 在未审批前，不允许自动扫描正文、不允许生成正式 Chunk、不允许写入正式 Qdrant；
- 可以在批准后用于只读 Source Discovery 和 Shadow 验证；
- 需要明确目录权限、文件所有人、保密边界和可纳入的子目录。

重点关联问题：

- BA-003：厂房产品线方案比选外部 DOCX；
- BA-006：2026 年设计与技术工作计划外部 PDF；
- BA-007：设计示范项目和工作计划外部 PDF；
- BA-009：2026 年 4 月设计服务台账外部 XLSX；
- BA-010：星谷科创中心价值创造清单外部 XLSX。

### Root-003：设计支持中心外部资料 Root

| 属性 | 值 |
|---|---|
| `root_id` | `Root-003` |
| `path` | `D:\工作\设计支持中心` |
| `owner` | 设计支持中心/企业设计支持责任部门 |
| `purpose` | 设计价值创造、产品线案例、方案比选案例、专业设计资料和设计管理支撑资料 |
| `read_only` | `true` |
| `approval_status` | `PENDING_APPROVAL`

说明：

- 与 Root-002 相同，当前只登记，不自动纳入；
- 优先用于核验产品线案例、设计创效案例和专业方案比选资料；
- 需要单独检查外部文件是否已迁移、是否重复、是否存在旧版本和权限限制。

## 4. Root 审批状态

建议采用以下状态：

```text
PENDING_APPROVAL
APPROVED_DISCOVERY_ONLY
APPROVED_SHADOW_READ
APPROVED_FORMAL_READ
SUSPENDED
REJECTED
```

状态含义：

| 状态 | 允许动作 |
|---|---|
| `PENDING_APPROVAL` | 只保存候选路径和引用关系，不读取正文 |
| `APPROVED_DISCOVERY_ONLY` | 只扫描文件名、size、mtime、sha256 和链接，不解析正文 |
| `APPROVED_SHADOW_READ` | 允许只读解析、Chunk、Embedding 和 Shadow Qdrant 验证 |
| `APPROVED_FORMAL_READ` | 经业务和安全审批后，允许进入正式发布流程 |
| `SUSPENDED` | 停止新扫描，保留历史审计记录 |
| `REJECTED` | 不得读取、解析或发布 |

推荐初始状态：

- Root-001：`APPROVED_SHADOW_READ`，维持当前实际运行能力；
- Root-002：`PENDING_APPROVAL`；
- Root-003：`PENDING_APPROVAL`。

## 5. 安全规则

### 5.1 禁止作为 Knowledge Root

以下路径及其子目录不得被配置为 Knowledge Root：

```text
D:\
C:\
用户目录，例如 C:\Users\...
系统目录，例如 C:\Windows\...
Program Files、ProgramData 等系统或应用目录
临时目录、缓存目录和模型目录
```

禁止使用盘符根目录作为扫描入口，禁止用模糊通配符扩大 Root 范围。

### 5.2 Root 边界校验

每次发现或解析前必须执行：

1. 规范化绝对路径；
2. 解析符号链接和 `..` 路径；
3. 检查路径是否位于已批准 Root 内；
4. 检查 `root_id` 与实际路径是否一致；
5. 检查文件是否为普通文件；
6. 记录越界路径，不执行读取；
7. 禁止通过 `file://`、外部绝对路径或 Wikilink 绕过 Root 审批。

### 5.3 只读与隐私边界

- 运行账户只授予读取权限；
- 不修改、移动、重命名或覆盖外部源文件；
- 不把外部源文件复制回 `D:\设计管理`；
- Shadow 缓存和索引必须与正式 Qdrant 分离；
- 日志不得输出 API Key、个人隐私和不必要的文件正文；
- Root 被暂停或撤销后，不得继续使用旧版本文件自动发布。

## 6. SourceRecord 增加字段

`SourceRecord` 必须增加：

```json
{
  "knowledge_root_id": "Root-002"
}
```

建议同时保留：

```json
{
  "root_path": "D:\\工作\\二公司技术部",
  "root_approval_status": "PENDING_APPROVAL",
  "inside_allowed_root": false,
  "source_status": "NEEDS_REVIEW",
  "approval_ticket": null,
  "owner": "二公司技术部",
  "discovery_policy_version": "v1"
}
```

`knowledge_root_id` 不得从文件名猜测，必须由经过规范化和审批的 Root Policy 解析得到。

## 7. NEEDS_REVIEW 处理规则

### 7.1 触发条件

以下情况统一进入 `NEEDS_REVIEW`：

- 目标路径位于 Root-002 或 Root-003，但 Root 尚未批准；
- 路径位于已知 Root 之外；
- 外部 PDF/DOCX/XLSX 实际存在，但不在允许 Root 内；
- 路径解析存在歧义；
- 目标是目录而不是普通文件；
- 同一文件存在多个 sha256 或版本冲突；
- source registration 与实际文件名不一致；
- 外部文件权限不足或读取异常；
- 发现疑似系统目录、用户目录或临时目录。

### 7.2 NEEDS_REVIEW 记录内容

必须记录：

- `source_id`；
- `knowledge_root_id`；
- `source_path`；
- `raw_link`；
- `exists`；
- `inside_allowed_root`；
- `reason_code`；
- `reason_message`；
- `requested_by`；
- `review_status`；
- `reviewed_by`；
- `reviewed_at`。

### 7.3 禁止行为

`NEEDS_REVIEW` 的 SourceRecord：

- 不得进入正式 Document Pipeline；
- 不得生成正式 Chunk；
- 不得生成正式 Embedding；
- 不得写入正式 Qdrant；
- 不得被 Citation 当作已验证正文；
- 不得因为 Retriever 命中路径登记页就自动升级为 `INDEXED`。

## 8. 后续 TASK-016B-2 多 Root 使用方式

### 8.1 扫描入口

后续实现应从 Root Policy 加载已批准 Root：

```text
Root Policy
  ↓ only approved roots
Source Discovery
  ↓ knowledge_root_id
Document Pipeline
  ↓ root-aware staging
Shadow Index
```

禁止让 Document Pipeline 直接扫描任意路径。所有文件必须先经过 Root Resolver。

### 8.2 多 Root 的数据隔离

每个 Staging/Shadow 记录必须保存：

- `knowledge_root_id`；
- `root_path`；
- `source_path`；
- `source_sha256`；
- `source_owner`；
- `approval_status`。

不同 Root 的文件即使文件名相同，也不得仅按 `file_name` 去重，必须按 `knowledge_root_id + normalized_path + sha256` 判断身份。

### 8.3 多 Root 的发布策略

建议分阶段：

1. Root-001 继续作为现有 Shadow 基线；
2. Root-002 单独构建 `shadow_root_002` 验证集；
3. Root-003 单独构建 `shadow_root_003` 验证集；
4. 分 Root 检查解析率、重复率、权威等级和 Citation 完整性；
5. 业务负责人确认后，再设计多 Root 合并 Shadow；
6. 正式发布前仍需保留按 Root 回滚和按 Root 下线能力。

## 9. 设计验收标准

本设计在进入 TASK-016B-2 前应满足：

1. Root-001、Root-002、Root-003 的 owner、用途、只读和审批状态明确；
2. Root-002、Root-003 未审批前不会被自动读取正文；
3. `knowledge_root_id` 能进入 SourceRecord、SourceLink、Staging 和未来 Chunk payload；
4. `NEEDS_REVIEW` 有明确原因和人工审批入口；
5. 禁止路径规则可以阻断盘符根目录、系统目录和用户目录；
6. 多 Root 不会按文件名错误合并不同来源文件；
7. 后续实现不需要修改 Retriever、8000 服务或正式 Qdrant。

**TASK-016B-1.5：Knowledge Source Root Approval Design 完成。**
