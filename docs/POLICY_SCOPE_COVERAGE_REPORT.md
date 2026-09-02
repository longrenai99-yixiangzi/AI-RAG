# Policy Scope Coverage Report

> TASK-017E-1.2：仅在 Shadow 环境验证 POLICY_QUERY 的多 Facet 覆盖；未修改 Retriever、Router、Preflight、Scope Guard、Query Page Probe、OPTION_QUERY、BA-010 Fact Path、正式 Qdrant 或 8000 服务。

## 1. Failure Stage

已确认主因是 `SEMANTIC_SCOPE_COVERAGE_LOSS`，发生在 `Candidate → Evidence Selection`：局级/二公司两个相关 Policy Facet 已进入候选，但基线 Evidence 只保留一个 Facet。
- Baseline selected facets：`['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']`
- Baseline missing facets：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`
- Optimized selected facets：`['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']`

## 2. Policy Scope Facets

Facet 由候选正文、文件路径、文件名中的组织层级、主题、子类型和年份推断；未使用 BA 编号、固定文件名作为 Facet 定义。

- query_scope_specificity：`UNSPECIFIED_SCOPE`
- organization_level：`['COMPANY', 'GROUP']`
- demonstration_type：`['DESIGN_MANAGEMENT', 'DETAILED_DESIGN']`

## 3. Selected Facets Before / After

| State | Selected Facets | Missing Facets | Coverage Complete | Action |
|---|---|---|---|---|
| Baseline | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `False` | `BASELINE_SINGLE_SELECTION` |
| Optimized | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `[]` | `True` | `FACET_PRESERVING_EVIDENCE` |

## 4. BA-007 Final Answer

当前问题未明确限定管理层级和示范项目类型，检索结果按 Policy Facet 分层展示：

1. GROUP/DESIGN_MANAGEMENT：— 2 — 中建三局2026 年设计与技术工作计划 2026 年是“十五五”开局之年，为更好落实集团决策部署、局 三会工作安排，设计与技术系统秉持以项目为中心，紧扣“完善 体系、建强能力、强化赋能”三大核心主线，聚焦激发系统内生 动力、推广优质创新成果、筑牢人才梯队根基，以中台能力全面 提升为抓手，持续强化设计技术服务支撑效能，谋划全年工作安 排，具体做好以下八个方面。 一、加强策划规划引领，提升“造项目”能力 城市规划与产业研究院要打造策划规划能力集成平台，并加 强与营销平台的联动，进一步筑牢局“咨-规-投-建-运”一体化 优势，强化策划规划在“造项目”中的引领作用。一是要推进大 师工作室建设，建立城市更新、文商旅等领域4 个大师工作室， 完善大师工作室运行机制及与局投资建造单位的协同机制，确保 高效运行。发挥大师引领作用，推动城市更新、文商旅类项目落 地。二是要加强专项领域研究，加强城市更新、文商旅等领域专 项研究，完成专题研究报告及策划规划方案示范文本。三是要深 化重大项目营销赋能，深度参与重大项目综合营销，总结提炼可 复制推广的合作模式，发布典型项目成套解决方案。四是要强化 高层次人才支撑，积极探索省级以上勘察设计大师等高层次人才 引进工作，打造策划规划品牌。 局属各单位要加强和城市规划与产业研究院互动，主动组装 资源，充分利用好规划院在方案规划、项目前期辅导方面的作用，  [S1]
2. COMPANY/DESIGN_MANAGEMENT：— 4 — 产业远程服务机制，聚焦江苏、湖北、安徽三大核心区域，云系、 碳系公司需深度参与主业公司重点项目前期营销与过程服务。 （四）持续推进示范项目建设 一是强化示范工程引领，以公司重点项目为依托，着力打造 科技、绿色、智能建造等方面的示范工程，立项局级及以上示范 （试点）项目不少于10 项，其中基础公司苏州北站、北京公司 雄安航天基地、浙江公司杭州四院等项目须立项省级科技示范项 目；主业公司须打造1 项Ⅱ级以上集团智能建造示范项目，专业 公司负责协同配合，其中直属公司圆融国际、土木公司老谷南等 项目，应争创集团Ⅲ级项目；二是强化创优项目保障，针对拟申 报国优、鲁班奖项目，各分公司应积极组织申报行业新技术及绿 色施工示范工程，及时完成验收取证；直属公司中医科、华南公 司天津佐治亚大学项目，应重点推进中施企协绿色施工水平评价 及中建协绿色建造施工竞赛验收工作，切实保障创优目标。 二、设计协同，提升服务效能 （一）完善设计管理体系 一是夯实中心组织建设，结合局对公司平台化履约调研意 见，公司继续加强设计支持中心建设，各主业公司在部门配齐配 强设计管理人员，确保建筑或结构专业设计工程师配置数量不低 于1 人，各专业公司补强专项设计支持能力，扎实推动中心建强 建优；二是健全设计联动机制，一季度发布《公司设计管理体系 建设评价指南》，为体系优化与能力提升提供量化依据；4 月发 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09: 刘畅 第二建设公司 2026-05-19 09:18  [S2]
3. GROUP/DETAILED_DESIGN：— 6 — 清单》。局属各单位一是要制定相应的BIM 应用能力提升实施细 则，健全BIM 应用体系，至少打造1 个BIM 应用示范项目，确保 《BIM 技术应用清单》应用率100%。二是要聚焦中心及项目技术 人员BIM 应用能力提升，以师带徒、以干代训，年底掌握BIM 技 术人员占比不低于30%。三是要在房建类EPC 项目应用BIM 建模， 覆盖率不少于50%，并应用模型开展全专业深化设计，出具工料 清单，为合约包打开提供支持。四是要积极参加局内外BIM 大赛 等技术比武活动，营造“比学赶超”的良好氛围。五是要积极探 索BIM+物联网、BIM+数字孪生、BIM+智慧运维等新场景应用， 提升三局在行业的影响力。 七、加强创新成果应用，提升科技赋能水平 在局一部五院多平台有组织科研体系下，5 大科研方向创新 成果持续产出，局层面将组织创新成果成熟度、经济性等评价， 形成智能建造、绿色低碳等产品与技术推广应用清单。局属单位 一是要加强创新成果设计导入，对设计系统开展局创新成果培 训，精准掌握创新成果适配场景与应用方法，在设计策划环节嵌 入创新产品和成果，让设计成为转化创新价值的关键载体。二是 要在落实局统一部署的基础上，制定自身的创新成果推广应用计 划，应用尽用、能用尽用，助力创新成果落地与更新迭代。三是 要落实建筑工业化“好房子”智能建造专项工作，地产开发项目 按照创新技术清单做好智能建造策划，严格按照建筑工业化“好 房子”系统解决方案策划审批流程报局审批，牵引智能建造技术 应用。四是要提升“好房子”建设水平，城投及壹品公司每月报 送新开地产项目“好房子”评价得分情况及下阶段提分举 [S3]
4. COMPANY/DETAILED_DESIGN：— 8 — 2.精准管控，抓实深化设计 一是制定能力提升方案，公司4 月前出台《深化设计能力建 设实施细则》，明确能力建设层级、全专业深化设计支持团队建 设方案，形成分阶段工作落地举措；二是加强深化计划管理，支 持中心牵头，组织项目、专业分包等相关人员，根据项目总体控 制计划，编制深化设计计划及配套的专项计划，过程中安排专人 负责预警管理，对存在重大风险计划项，通过函件、协调会等形 式协调纠偏，确保计划按期完成；三是健全分包准入资格，遴选 深化设计单位时严格考察其专业设计能力，在合同中明确准入资 格及切割条款；建立外部咨询单位应急进场机制，当专业分包设 计能力不足时及时启动，实现风险止损；四是做好全专业设计协 同，分公司组织支持中心、外部咨询单位，对图纸进行审核，针 对各专业间碰撞检查，各主业公司在中心配置专人，在实践中持 续强化综合合模叠图能力，统筹各专业间管理；五是提升BIM 应用能力，公司组织技术支持中心及各项目全体技术人员参与局 BIM 技能认证考试，结合考试内容开展考前培训，确保局BIM 认 证率不低于50%；各分公司要打造至少1 个BIM 应用示范项目， 示范项目要依托BIM 开展全专业的深化设计，100%应用局《BIM 技术应用清单》；房建类EPC 项目必须完成项目BIM 模型并上传 至DOP 系统AI 图模管理板块，并通过BIM 技术开展主要专业碰 撞检查工作，形成碰撞检查报告。 3.靶向施策，管控资料试验 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09: [S4]

上述要求属于不同管理层级或示范项目类型，不能在未限定范围时合并为同一条要求。

### Atomic Claims

- `C1` / `POLICY_FACET` / facet=`GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / evidence=`['S1']`：GROUP/DESIGN_MANAGEMENT：— 2 — 中建三局2026 年设计与技术工作计划 2026 年是“十五五”开局之年，为更好落实集团决策部署、局 三会工作安排，设计与技术系统秉持以项目为中心，紧扣“完善 体系、建强能力、强化赋能”三大核心主线，聚焦激发系统内生 动力、推广优质创新成果、筑牢人才梯队根基，以中台能力全面 提升为抓手，持续强化设计技术服务支撑效能，谋划全年工作安 排，具体做好以下八个方面。 一、加强策划规划引领，提升“造项目”能力 城市规划与产业研究院要打造策划规划能力集成平台，并加 强与营销平台的联动，进一步筑牢局“咨-规-投-建-运”一体化 优势，强化策划规划在“造项目”中的引领作用。一是要推进大 师工作室建设，建立城市更新、文商旅等领域4 个大师工作室， 完善大师工作室运行机制及与局投资建造单位的协同机制，确保 高效运行。发挥大师引领作用，推动城市更新、文商旅类项目落 地。二是要加强专项领域研究，加强城市更新、文商旅等领域专 项研究，完成专题研究报告及策划规划方案示范文本。三是要深 化重大项目营销赋能，深度参与重大项目综合营销，总结提炼可 复制推广的合作模式，发布典型项目成套解决方案。四是要强化 高层次人才支撑，积极探索省级以上勘察设计大师等高层次人才 引进工作，打造策划规划品牌。 局属各单位要加强和城市规划与产业研究院互动，主动组装 资源，充分利用好规划院在方案规划、项目前期辅导方面的作用， 
- `C2` / `POLICY_FACET` / facet=`COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / evidence=`['S2']`：COMPANY/DESIGN_MANAGEMENT：— 4 — 产业远程服务机制，聚焦江苏、湖北、安徽三大核心区域，云系、 碳系公司需深度参与主业公司重点项目前期营销与过程服务。 （四）持续推进示范项目建设 一是强化示范工程引领，以公司重点项目为依托，着力打造 科技、绿色、智能建造等方面的示范工程，立项局级及以上示范 （试点）项目不少于10 项，其中基础公司苏州北站、北京公司 雄安航天基地、浙江公司杭州四院等项目须立项省级科技示范项 目；主业公司须打造1 项Ⅱ级以上集团智能建造示范项目，专业 公司负责协同配合，其中直属公司圆融国际、土木公司老谷南等 项目，应争创集团Ⅲ级项目；二是强化创优项目保障，针对拟申 报国优、鲁班奖项目，各分公司应积极组织申报行业新技术及绿 色施工示范工程，及时完成验收取证；直属公司中医科、华南公 司天津佐治亚大学项目，应重点推进中施企协绿色施工水平评价 及中建协绿色建造施工竞赛验收工作，切实保障创优目标。 二、设计协同，提升服务效能 （一）完善设计管理体系 一是夯实中心组织建设，结合局对公司平台化履约调研意 见，公司继续加强设计支持中心建设，各主业公司在部门配齐配 强设计管理人员，确保建筑或结构专业设计工程师配置数量不低 于1 人，各专业公司补强专项设计支持能力，扎实推动中心建强 建优；二是健全设计联动机制，一季度发布《公司设计管理体系 建设评价指南》，为体系优化与能力提升提供量化依据；4 月发 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09: 刘畅 第二建设公司 2026-05-19 09:18 
- `C3` / `POLICY_FACET` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / evidence=`['S3']`：GROUP/DETAILED_DESIGN：— 6 — 清单》。局属各单位一是要制定相应的BIM 应用能力提升实施细 则，健全BIM 应用体系，至少打造1 个BIM 应用示范项目，确保 《BIM 技术应用清单》应用率100%。二是要聚焦中心及项目技术 人员BIM 应用能力提升，以师带徒、以干代训，年底掌握BIM 技 术人员占比不低于30%。三是要在房建类EPC 项目应用BIM 建模， 覆盖率不少于50%，并应用模型开展全专业深化设计，出具工料 清单，为合约包打开提供支持。四是要积极参加局内外BIM 大赛 等技术比武活动，营造“比学赶超”的良好氛围。五是要积极探 索BIM+物联网、BIM+数字孪生、BIM+智慧运维等新场景应用， 提升三局在行业的影响力。 七、加强创新成果应用，提升科技赋能水平 在局一部五院多平台有组织科研体系下，5 大科研方向创新 成果持续产出，局层面将组织创新成果成熟度、经济性等评价， 形成智能建造、绿色低碳等产品与技术推广应用清单。局属单位 一是要加强创新成果设计导入，对设计系统开展局创新成果培 训，精准掌握创新成果适配场景与应用方法，在设计策划环节嵌 入创新产品和成果，让设计成为转化创新价值的关键载体。二是 要在落实局统一部署的基础上，制定自身的创新成果推广应用计 划，应用尽用、能用尽用，助力创新成果落地与更新迭代。三是 要落实建筑工业化“好房子”智能建造专项工作，地产开发项目 按照创新技术清单做好智能建造策划，严格按照建筑工业化“好 房子”系统解决方案策划审批流程报局审批，牵引智能建造技术 应用。四是要提升“好房子”建设水平，城投及壹品公司每月报 送新开地产项目“好房子”评价得分情况及下阶段提分举
- `C4` / `POLICY_FACET` / facet=`COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / evidence=`['S4']`：COMPANY/DETAILED_DESIGN：— 8 — 2.精准管控，抓实深化设计 一是制定能力提升方案，公司4 月前出台《深化设计能力建 设实施细则》，明确能力建设层级、全专业深化设计支持团队建 设方案，形成分阶段工作落地举措；二是加强深化计划管理，支 持中心牵头，组织项目、专业分包等相关人员，根据项目总体控 制计划，编制深化设计计划及配套的专项计划，过程中安排专人 负责预警管理，对存在重大风险计划项，通过函件、协调会等形 式协调纠偏，确保计划按期完成；三是健全分包准入资格，遴选 深化设计单位时严格考察其专业设计能力，在合同中明确准入资 格及切割条款；建立外部咨询单位应急进场机制，当专业分包设 计能力不足时及时启动，实现风险止损；四是做好全专业设计协 同，分公司组织支持中心、外部咨询单位，对图纸进行审核，针 对各专业间碰撞检查，各主业公司在中心配置专人，在实践中持 续强化综合合模叠图能力，统筹各专业间管理；五是提升BIM 应用能力，公司组织技术支持中心及各项目全体技术人员参与局 BIM 技能认证考试，结合考试内容开展考前培训，确保局BIM 认 证率不低于50%；各分公司要打造至少1 个BIM 应用示范项目， 示范项目要依托BIM 开展全专业的深化设计，100%应用局《BIM 技术应用清单》；房建类EPC 项目必须完成项目BIM 模型并上传 至DOP 系统AI 图模管理板块，并通过BIM 技术开展主要专业碰 撞检查工作，形成碰撞检查报告。 3.靶向施策，管控资料试验 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09:18 刘畅 第二建设公司 2026-05-19 09:
- `C5` / `SCOPE_BOUNDARY` / facet=`None` / evidence=`['S1', 'S2', 'S3', 'S4']`：上述要求属于不同管理层级或示范项目类型，不能在未限定范围时合并为同一条要求。

### Citation

- `S1` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 2, 'text_length': 888}` / facet=`GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / origin=RRF,BM25,DENSE
- `S2` 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf / `{'page': 4, 'text_length': 857}` / facet=`COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026` / origin=RRF,BM25,DENSE
- `S3` 关于印发中建三局2026年设计与技术工作计划的通知.pdf / `{'page': 6, 'text_length': 967}` / facet=`GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / origin=RRF,BM25,DENSE
- `S4` 关于印发中建三局第二建设公司2026年设计与技术（科技）工作计划的通知.pdf / `{'page': 8, 'text_length': 885}` / facet=`COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026` / origin=RRF,BM25
- `S5` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / facet=`None` / origin=RRF,BM25,DENSE
- `S6` 公司复盘EPC项目管理台账.xlsx / `{'sheet_name': 'Sheet3', 'row_start': 1, 'row_end': 43, 'column_count': 4, 'header_row': 1}` / facet=`None` / origin=RRF,BM25,DENSE

## 5. BA-001 / BA-003 / BA-005 Regression

| BA | Preflight/Existing Status | Final Status | Provider Calls |
|---|---|---|---:|
| BA-001 | `READY_FOR_GENERATION` | `PROVIDER_TEMPORARY_FAILURE` | `3` |
| BA-003 | `SOURCE_SCOPE_MISSING` | `NO_EVIDENCE` | `0` |
| BA-005 | `AUTHORITY_INSUFFICIENT` | `NO_EVIDENCE` | `0` |

BA-002/BA-004/BA-008/BA-010 仅读取既有结果做兼容性检查，未由本任务重写。

## 6. 12题通用 Scope 测试

| Test | Specificity | Candidate Facets | Before | After | Result |
|---|---|---:|---|---|---|
| PSC-001 | EXPLICIT_SCOPE | 4 | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | PASS |
| PSC-002 | EXPLICIT_SCOPE | 4 | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-003 | UNSPECIFIED_SCOPE | 4 | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-004 | EXPLICIT_SCOPE | 4 | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | PASS |
| PSC-005 | EXPLICIT_SCOPE | 3 | `['COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `['GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-006 | EXPLICIT_SCOPE | 4 | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `[]` | PASS |
| PSC-007 | PARTIAL_SCOPE | 4 | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-008 | PARTIAL_SCOPE | 3 | `[]` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-009 | PARTIAL_SCOPE | 4 | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-010 | UNSPECIFIED_SCOPE | 4 | `['GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-011 | PARTIAL_SCOPE | 3 | `['COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026']` | PASS |
| PSC-012 | PARTIAL_SCOPE | 4 | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | `['COMPANY/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026', 'COMPANY/DEMONSTRATION_PROJECT/DETAILED_DESIGN/2026', 'GROUP/DEMONSTRATION_PROJECT/DESIGN_MANAGEMENT/2026']` | PASS |

- 测试通过：`12/12`
- Evidence Location 完整：`12/12`
- 明确范围问题只保留对应 Scope；未明确范围问题保留多个合理 Facet。

## 7. Compatibility Snapshot

- BA-002：`GENERATED`
- BA-004：`GENERATED`
- BA-008：`GENERATED`
- BA-010：`FACT_RESULT`

## 8. 结论

BA-007 优化后覆盖完整：`True`。未限定范围时采用 `FACET_PRESERVING_EVIDENCE` 分层回答；明确范围时不扩展到其他管理层级。程序保留原文遮蔽的百分比/金额，不做猜测。
