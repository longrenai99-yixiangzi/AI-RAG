import type { KnowledgeNode } from '../../types/knowledge'
import type { KnowledgeCardRecord, KnowledgeCaseRecord, KnowledgeNodeSample, KnowledgeSourceRecord } from './knowledgeContent'

type LeafDefinition = {
  title: string
  summary: string
  keyPoints: string[]
  sourceIds: string[]
  contentStatus?: '已抽取' | '待核原文'
  managementPoints?: string[]
}

export const designManagementCategorySeeds: Array<[string, string, string[]]> = [
  ['system', '01 设计管理体系', ['01.01 管理制度', '01.02 管理标准', '01.03 管理流程', '01.04 岗位职责', '01.05 管理动作', '01.06 考核评价']],
  ['bid', '02 投标与前期设计管理', ['02.01 投标设计管理', '02.02 项目设计条件分析', '02.03 设计合同与界面', '02.04 设计资源配置', '02.05 前期设计风险']],
  ['planning', '03 设计策划管理', ['03.01 设计评估', '03.02 设计管理策划', '03.03 设计任务书', '03.04 设计计划', '03.05 方案比选', '03.06 设计价值创造点']],
  ['process', '04 设计过程管理', ['04.01 方案设计管理', '04.02 初步设计管理', '04.03 施工图设计管理', '04.04 设计进度管理', '04.05 设计提资管理', '04.06 专业协调管理', '04.07 设计会议与沟通']],
  ['deliverables', '05 阶段性设计成果管理', ['05.01 设计成果审查', '05.02 审查意见闭环', '05.03 设计变更管理', '05.04 设计成果版本管理', '05.05 设计成果交付']],
  ['result-library', '06 设计成果库', ['06.01 方案比选案例库', '06.02 设计指标库', '06.03 设计价值创造点库', '06.04 典型问题库', '06.05 标准做法库', '06.06 项目复盘成果库']],
  ['resource', '07 设计资源库', ['07.01 设计院资源', '07.02 设计大师（专家）资源']],
  ['materials', '08 设计资料库', ['08.01 规范标准', '08.02 标准图集', '08.03 标准节点', '08.04 模板表单', '08.05 标准化成果', '08.06 参考资料']],
]

const source = (id: string, name: string, type: string, sourcePath: string, location: string, excerpt: string): KnowledgeSourceRecord => ({ id, name, type, authority: '知识提炼', sourcePath, location, excerpt })
const wiki = (name: string) => `D:/设计管理/wiki/concepts/${name}`

const sourceCatalog: Record<string, KnowledgeSourceRecord> = {
  'ds-standard': source('ds-standard', '建设标准库（知识提炼页）', '标准库', wiki('设计支持/建设标准库.md'), '摘要 / 核心要点', '建设标准库是二公司“法人管项目”管控体系下 4、成果输出 → 4.1 知识库建设的核心子库，按 6 条产品线组织。'),
  'ds-planning': source('ds-planning', '设计策划（知识提炼页）', '策划方法', wiki('设计支持/设计策划.md'), '核心要点 / 策划内容', '设计策划是项目设计阶段的总体规划和工作部署，包括设计管理目标、组织架构、工作流程、资源配置、风险管理等方面的策划工作。'),
  'ds-evaluate': source('ds-evaluate', '设计评估（知识提炼页）', '评估方法', wiki('设计支持/设计评估.md'), '核心要点 / 评估类型', '设计评估是对设计过程和设计成果进行系统评价的工作，包括设计方案评审、设计质量评估、设计进度评估等内容。'),
  'ds-task': source('ds-task', '设计任务书（知识提炼页）', '任务书', wiki('设计支持/设计任务书.md'), '核心要点 / 编制内容', '设计任务书是设计管理中的核心文件，明确项目设计目标、范围、技术标准、进度要求等内容，是设计工作开展和设计合同管理的基础依据。'),
  'ds-procurement': source('ds-procurement', '设计招采（知识提炼页）', '招采管理', wiki('设计支持/设计招采.md'), '核心要点 / 管理流程', '设计招采包括供应商选择、合同谈判、履约管理等内容；管理流程为需求确认 → 招标文件编制 → 投标评审 → 合同签订 → 履约管理。'),
  'ds-risk': source('ds-risk', '设计风险（知识提炼页）', '风险管理', wiki('设计支持/设计风险.md'), '核心要点 / 管理流程', '设计风险管理流程为风险识别 → 风险评估 → 风险应对 → 风险监控，工具包括风险清单、风险评估矩阵和风险预警机制。'),
  'ds-plan': source('ds-plan', '设计计划（知识提炼页）', '计划管理', wiki('设计支持/设计计划.md'), '核心要点 / 计划内容', '设计计划明确设计各阶段的时间节点、里程碑、资源安排和控制措施，管理流程为计划编制 → 审核批准 → 执行跟踪 → 偏差分析 → 调整优化。'),
  'ds-value': source('ds-value', '设计价值创造（知识提炼页）', '价值创造', wiki('设计支持/设计价值创造.md'), '核心要点 / 工作流程', '设计价值创造的工作流程为识别价值点 → 分析可行性 → 实施优化 → 验证效果，量化指标包括造价节约、工期缩短、品质提升、运维成本降低。'),
  'ds-compare': source('ds-compare', '方案比选（知识提炼页）', '方案比选', wiki('设计支持/方案比选.md'), '核心要点 / 比选流程', '方案比选是在设计阶段对多个设计方案进行技术经济比较、分析论证，工作流程为明确比选目标 → 编制比选方案 → 组织评审 → 形成结论。'),
  'ds-compare-library': source('ds-compare-library', '方案比选库（知识提炼页）', '案例库', wiki('设计支持/方案比选库.md'), '核心要点 / 标准化提示清单', '方案比选库提供方案比选的标准化提示清单与创效比选实例，字段包括专业类别、比选项目、方案、技术与商务分析、比选结果和比选阶段。'),
  'ds-limit': source('ds-limit', '限额设计（知识提炼页）', '限额设计', wiki('设计支持/限额设计.md'), '核心要点 / 控制方法', '限额设计以投资控制为目标，在设计过程中分阶段、分专业控制造价，控制方法为投资分解 → 限额分配 → 设计优化 → 对比验证。'),
  'ds-cost': source('ds-cost', '控概与概算（知识提炼页）', '概算控制', wiki('设计支持/控概与概算.md'), '核心要点 / 控概逻辑', '控概逻辑为投资估算 → 估算复核 → 概算策划 → 概算复核 → 预算编制及复核，设计与商务需要紧密联动。'),
  'ds-quality': source('ds-quality', '设计质量（知识提炼页）', '质量管理', wiki('设计支持/设计质量.md'), '核心要点 / 质量控制', '设计质量控制内容包括设计接口管理、设计认质认样和阶段性成果管理，手段包括设计审查、设计交底、设计变更管理和质量巡检。'),
  'ds-communication': source('ds-communication', '相关方沟通机制（知识提炼页）', '沟通机制', wiki('设计支持/相关方沟通机制.md'), '核心要点 / 管理机制', '相关方沟通机制包括沟通计划、联络人制度、信息传递流程和问题反馈闭环，沟通对象包括建设单位、设计院、施工单位、分包单位和政府主管部门。'),
  'ds-approval': source('ds-approval', '报批报建（知识提炼页）', '报批报建', wiki('设计支持/报批报建.md'), '核心要点 / 关键工作', '报批报建关键工作包括报批计划编制、资料准备、审批跟踪和问题协调，覆盖前期、施工和验收阶段。'),
  'ds-complex': source('ds-complex', '复杂专项与地标（知识提炼页）', '专项管理', wiki('设计支持/复杂专项与地标.md'), '核心要点 / 一体化设计协同', '复杂专项与地标项目的设计管理难点在于多专业一体化协同与专项工艺落地，涉及体育工艺、超高层、数据中心和智能建造等类型。'),
  'ds-review': source('ds-review', '设计复盘（知识提炼页）', '复盘方法', wiki('设计管理成果总结/设计复盘.md'), '复盘涉及的项目', '设计复盘是项目完工或阶段结束后，对设计管理全过程进行回顾、总结和反思的工作方法，旨在提炼经验教训，形成知识沉淀。'),
  'ds-toolbook': source('ds-toolbook', '管理工具书（知识提炼页）', '工具书', wiki('设计管理成果总结/管理工具书.md'), '涵盖内容', '管理工具书是二公司设计管理部积累的一系列标准化工作工具和方法指南的集合，涵盖建设标准、报批报建指标、施工图审核、设计指标、风险清单等。'),
  'ds-construction-review': source('ds-construction-review', '施工图审核要点（知识提炼页）', '成果审查', wiki('设计管理成果总结/管理工具书/施工图审核要点.md'), '页面摘要', '施工图审核要点是对施工图设计成果进行审查的标准和关注点汇总，目标是确保施工图设计质量。'),
  'ds-indicator': source('ds-indicator', '设计指标库（知识提炼页）', '指标库', wiki('设计管理成果总结/管理工具书/设计指标库.md'), '页面摘要', '设计指标库是各类型项目设计技术经济指标的汇总数据库，为项目方案比选、限额设计提供参考基准。'),
  'ds-template': source('ds-template', '示范文本（知识提炼页）', '模板表单', wiki('设计管理成果总结/管理工具书/示范文本.md'), '页面摘要', '示范文本是设计管理中各类标准文件模板的集合，为项目设计管理文件的规范化编制提供参考。'),
  'ds-duration': source('ds-duration', '设计标准工期库（知识提炼页）', '工期库', wiki('设计管理成果总结/管理工具书/设计标准工期库.md'), '页面摘要', '设计标准工期库是各类型项目设计周期的标准参考数据库，为设计计划编制和进度管理提供依据。'),
  'ds-optimize': source('ds-optimize', '设计优化实施案例（知识提炼页）', '优化案例', wiki('设计管理成果总结/管理工具书/设计优化实施案例.md'), '页面摘要', '设计优化实施案例是通过方案优化实现价值创造的典型案例汇总，体现设计管理对项目的增值作用。'),
  'ds-cases': source('ds-cases', '设计创效案例库（知识提炼页）', '创效案例', wiki('设计支持/设计创效案例库.md'), '核心要点 / 案例结构', '设计创效案例按项目名称 → 专业 → 设计阶段 → 问题分析 → 优化方案 → 实施效果组织，效果从设计、建造、商务三个维度评估。'),
  'ds-resource': source('ds-resource', '设计资源库（知识提炼页）', '资源库', wiki('设计资源库/设计资源库.md'), '资源分类四维度', '设计资源按勘察设计资质、专项设计类型、推荐项目类型和单位或人员地域四个维度分类。'),
  'ds-institute': source('ds-institute', '设计院台账（知识提炼页）', '设计院台账', wiki('设计资源库/设计院台账.md'), '页面摘要', '设计院台账是二公司合作设计院的分类统计、对接分工和维护记录汇总。'),
  'ds-strategy': source('ds-strategy', '战略合作协议（知识提炼页）', '合作资源', wiki('设计资源库/战略合作协议.md'), '合作单位', '战略合作协议汇总反映公司的设计资源网络和合作关系，合作单位包括设计院和政府等。'),
}

const card = (id: string, title: string, summary: string, keyPoints: string[], sourceIds: string[], contentStatus: '已抽取' | '待核原文' = '已抽取'): KnowledgeCardRecord => ({ id, title, summary, keyPoints, sourceIds, contentStatus })

const leafDefinitions: Record<string, LeafDefinition> = {
  'design-system-1': { title: '制度性文件的组成', summary: '制度性文件构成设计管理体系的制度基础，当前知识页列出了建设方案、实施细则、设计支持管理细则、能力建设指导意见和绩效实施细则等来源。', keyPoints: ['建设方案与实施细则构成组织运行依据', '设计支持管理细则明确支持边界', '工作计划与管理指南作为关联内容继续展开'], sourceIds: ['dms-01'], managementPoints: ['先区分制度依据、管理机制、检查评价和结果应用，避免把案例或培训资料当成制度条款。', '涉及正式制度条文时，应继续回查原始制度文件，当前知识提炼页不能替代原文审批。', '检查发现的问题应进入培训、帮扶和下一期验证，形成可追踪的管理闭环。'] },
  'design-system-2': { title: '建设标准的体系化组织', summary: '建设标准库按产品线组织设计输入、交付标准与技术经济基准，服务设计质量控制和前期商务管理。', keyPoints: ['现有产品线包括体育场馆、医疗建筑、商业办公、基础设施、学校建筑和电子厂房', '整体系统性标准与功能性交付标准分层组织', '标准可作为设计输入、审核评价和限额划分依据'], sourceIds: ['ds-standard'] },
  'design-system-3': { title: '设计管理流程主线', summary: '现有知识页将设计管理流程拆为项目分析、目标确定、方案编制、评审确认和动态调整等环节，并与设计计划、任务书和评估衔接。', keyPoints: ['项目分析是策划和设计输入的起点', '评审确认把过程成果转为可执行依据', '重大变化需要动态调整并保留记录'], sourceIds: ['ds-planning', 'ds-plan'] },
  'design-system-4': { title: '法人管项目职责与界面', summary: '法人管项目由公司后台统筹支撑项目设计管理，知识页明确设计管理、设计支持、投标履约支持、知识沉淀和工作界面协同五类职责。', keyPoints: ['后台监督策划执行、成果评审、出图进度和培训', '建设标准库、设计知识库和技术知识库承担知识沉淀', '公司中心、分公司和项目部需要保持工作界面清晰'], sourceIds: ['dms-02'] },
  'design-system-5': { title: '设计管理标准化动作', summary: '设计策划评审实例展示了策划书编制、评审会议、督办清单、责任人和完成时限如何形成管理动作闭环。', keyPoints: ['策划书包含项目概况、目标、组织、合约、风险、比选、创效和报批报建', '评审意见转化为有责任部门、人和时限的督办清单', '重大变化需要分公司与公司确认后调整'], sourceIds: ['ds-planning', 'dms-03'] },
  'design-system-6': { title: '检查评价与结果应用', summary: '设计管理检查评价机制通过定期专项检查通报和项目级评价表量化管理水平，并将问题转化为帮扶、培训和下一期验证。', keyPoints: ['评价表按 100 分制组织多个管理维度', '检查结果形成排名、问题清单和帮扶计划', '检查发现问题 → 培训补强 → 下期检查验证'], sourceIds: ['dms-03', 'dms-07'] },
  'design-bid-1': { title: '设计招采的管理范围', summary: '设计招采覆盖方案设计、施工图设计、专项设计和技术咨询等采购范围，核心是把设计需求转化为可评审、可履约的采购条件。', keyPoints: ['明确采购范围和设计限额', '从资质、经验、团队、报价和服务承诺评价供应商', '合同中关注知识产权和设计变更条款'], sourceIds: ['ds-procurement'] },
  'design-bid-2': { title: '项目设计条件分析', summary: '设计评估知识页提供了项目设计条件分析的基本框架，可从技术、经济、可施工性、合规和进度五个维度建立设计输入判断。', keyPoints: ['先核实项目基础资料和约束条件', '通过专家评审、对标分析和价值工程形成判断', '评估结果作为后续优化和策划依据'], sourceIds: ['ds-evaluate'] },
  'design-bid-3': { title: '设计范围与合同界面', summary: '设计任务书是设计合同管理的基础依据，需把项目范围、技术标准、进度和交付成果写清，并作为合同附件管理。', keyPoints: ['区分方案、施工图和专项设计任务书', '明确设计边界、接口和交付成果', '通过审核、批准、交底和变更管理保持界面有效'], sourceIds: ['ds-task', 'ds-quality'] },
  'design-bid-4': { title: '设计资源配置', summary: '设计资源库将设计单位和专家资源按资质、专项类型、项目类型和地域分类，为前期设计招采和方案评审提供供方池。', keyPoints: ['按项目产品类型匹配设计能力', '核实资质、典型业绩和人员条件', '局平台清单与公司资源台账需要定期维护'], sourceIds: ['ds-resource'] },
  'design-bid-5': { title: '前期设计风险识别', summary: '前期风险节点以风险识别、评估、应对和监控为主线，重点关注进度、质量、变更、合规和成本风险。', keyPoints: ['建立前期风险清单和评估矩阵', '提前识别设计变更和多方协调风险', '对高风险事项设置预警与跟踪责任'], sourceIds: ['ds-risk'] },
  'design-planning-1': { title: '设计评估的类型与方法', summary: '设计评估覆盖方案评审、初步设计评审、施工图审查和设计后评估，输出用于设计优化、管理改进和知识积累。', keyPoints: ['技术合理性与经济性并重', '关注可施工性、合规性和进度符合性', '通过专家评审、对标分析和审查会议形成结论'], sourceIds: ['ds-evaluate'] },
  'design-planning-2': { title: '设计管理策划书', summary: '设计策划以目标、组织、流程、资源和风险为核心，形成项目设计阶段的总体规划和工作部署。', keyPoints: ['项目分析后确定设计管理目标', '成果包括策划书、项目管理计划和实施方案', '评审确认后根据重大变化动态调整'], sourceIds: ['ds-planning'] },
  'design-planning-3': { title: '设计任务书内容结构', summary: '设计任务书把设计目标、范围、技术标准、进度和成果要求固化为设计执行与合同管理依据。', keyPoints: ['包含项目概况、设计范围、技术标准、进度计划和交付成果', '按方案、施工图和专项设计分类', '形成编制、审核、批准、交底、执行和变更闭环'], sourceIds: ['ds-task'] },
  'design-planning-4': { title: '设计计划与里程碑', summary: '设计计划围绕阶段节点、责任人、交付成果和关键里程碑组织，并用偏差分析驱动调整优化。', keyPoints: ['编制依据包括总体进度、合同要求和设计任务书', '跟踪设计完成率和按时交付率', '计划变更应保留原因和调整记录'], sourceIds: ['ds-plan', 'ds-duration'] },
  'design-planning-5': { title: '方案比选工作方法', summary: '方案比选通过多个方案的技术经济比较和评审，平衡技术可行性、经济合理性、施工便利性、工期和运维成本。', keyPoints: ['先明确比选目标和评价维度', '形成技术与商务分析', '成果包括比选报告、分析表和会议纪要'], sourceIds: ['ds-compare'] },
  'design-planning-6': { title: '设计价值创造流程', summary: '设计价值创造以识别价值点、分析可行性、实施优化和验证效果为流程，关注造价、工期、品质和运维等增值维度。', keyPoints: ['方案、材料设备和施工工艺均可成为价值点', '价值工程与成本效益分析支撑决策', '最终需要回到实施效果验证'], sourceIds: ['ds-value', 'ds-cases'] },
  'design-process-1': { title: '方案设计阶段管理', summary: '方案设计阶段应把项目条件、建设标准、价值点和报批要求转化为可评审的设计方案。', keyPoints: ['方案评估与对标分析前置', '同步识别方案比选和报批报建事项', '方案结论需要与投资和后续实施衔接'], sourceIds: ['ds-evaluate', 'ds-standard', 'ds-approval'] },
  'design-process-2': { title: '初步设计阶段管理', summary: '初步设计阶段重点验证技术方案、功能配置、概算控制与各专业接口，为施工图和报批提供稳定输入。', keyPoints: ['核对初设成果与设计任务书', '结合建设标准和限额设计进行技术经济校核', '重大问题通过评审形成闭环'], sourceIds: ['ds-evaluate', 'ds-limit'] },
  'design-process-3': { title: '施工图设计管理', summary: '施工图管理以成果完整性、专业接口、可施工性和合规性为核心，并通过审查、交底和变更管理控制质量。', keyPoints: ['设计输入输出需要可核查', '施工图审查关注错漏碰缺和专业协调', '审查意见应进入闭环记录'], sourceIds: ['ds-quality', 'ds-construction-review'] },
  'design-process-4': { title: '设计进度控制', summary: '设计进度管理以计划和里程碑为主线，结合标准工期、交付成果和偏差分析持续纠偏。', keyPoints: ['明确各阶段节点和责任人', '跟踪按时交付率和计划变更', '滞后事项要分析原因并调整计划'], sourceIds: ['ds-plan', 'ds-duration'] },
  'design-process-5': { title: '设计提资管理', summary: '设计提资是专业和主体设计之间的信息传递机制，需要明确输入、输出、责任和时限，降低错漏碰缺风险。', keyPoints: ['提资资料应满足专业设计输入要求', '联络人制度保证信息传递连续', '问题反馈必须形成闭环'], sourceIds: ['ds-quality', 'ds-communication'] },
  'design-process-6': { title: '多专业协调管理', summary: '多专业协调以界面划分、信息同步和问题闭环为重点，服务复杂项目和全过程设计质量控制。', keyPoints: ['提前识别主体与专项设计界面', '用会议、书面函件和线上协同同步信息', '重大接口问题要保留责任和处理结果'], sourceIds: ['ds-communication', 'ds-complex'] },
  'design-process-7': { title: '设计会议与汇报机制', summary: '双月会、设计管理推进会、周报月报和季度检查等机制，为设计管理任务推进和问题协调提供固定载体。', keyPoints: ['双月会承担局或公司层面的沟通', '推进会服务项目和部门的过程推进', '周报月报提供常态化进展反馈'], sourceIds: ['dms-05'] },
  'design-deliverables-1': { title: '设计成果审查', summary: '设计成果审查围绕符合性、完整性、可施工性、经济性和创新性开展，覆盖接口、认质认样和阶段性成果。', keyPoints: ['按阶段成果和审查要点组织检查', '关注专业接口与设计输入输出', '审查结论成为后续交底和执行依据'], sourceIds: ['ds-quality', 'ds-construction-review'] },
  'design-deliverables-2': { title: '审查意见闭环', summary: '审查意见需要明确问题、责任、措施和完成时限，并在后续复核中确认处理结果，避免只形成会议记录。', keyPoints: ['意见要能对应具体成果和位置', '建立责任人、完成时间和验证状态', '未闭环事项应进入风险或推进台账'], sourceIds: ['ds-quality', 'dms-07'] },
  'design-deliverables-3': { title: '设计变更管理', summary: '设计变更管理需要识别变更原因，评估对质量、进度、成本和合同界面的影响，再履行确认和记录流程。', keyPoints: ['变更前评估影响范围', '与相关方及时沟通并保留确认依据', '重大变更纳入风险监控和结果复盘'], sourceIds: ['ds-risk', 'ds-communication'] },
  'design-deliverables-4': { title: '设计成果版本管理', summary: '当前知识页尚未形成独立版本管理制度正文；现有设计质量资料已明确阶段性成果管理和设计输入输出控制，可作为后续补齐入口。', keyPoints: ['需要建立版本号、发布日期和替换关系', '版本变更应能回查影响的成果和审查意见', '当前节点标记为待补齐，不把文件更新时间当作版本结论'], sourceIds: ['ds-quality'], contentStatus: '待核原文' },
  'design-deliverables-5': { title: '设计成果交付', summary: '成果交付应以任务书和合同约定为边界，检查成果完整性、专业接口、交付格式和接收确认。当前库内尚未形成独立交付制度正文。', keyPoints: ['核对交付成果清单和版本', '确认专业间接口和可施工性', '交付确认与后续变更记录需要关联'], sourceIds: ['ds-task', 'ds-quality'], contentStatus: '待核原文' },
  'design-result-library-1': { title: '方案比选案例库', summary: '方案比选库沉淀标准化提示清单和创效比选实例，便于新项目按专业、阶段和评价维度复用。', keyPoints: ['清单字段覆盖专业、方案、技术商务分析和结果', '实例记录工期、成本、质量、安全和社会效益', '比选结果与限额设计、设计评估衔接'], sourceIds: ['ds-compare-library'] },
  'design-result-library-2': { title: '设计指标库', summary: '设计指标库聚合各类型项目的设计技术经济指标，为方案比选和限额设计提供参考基准。', keyPoints: ['指标需要注明项目类型和适用条件', '指标是参考基准，不直接替代项目复核', '与设计标准工期库形成工具组合'], sourceIds: ['ds-indicator'] },
  'design-result-library-3': { title: '设计价值创造点库', summary: '价值创造点库将通用价值创造方法与产品线案例连接，支撑设计策划阶段识别可迁移的价值点。', keyPoints: ['价值点可来自方案、材料设备和施工工艺优化', '应记录问题、方案、实施效果和适用条件', '金额和效益需回查具体项目原始记录'], sourceIds: ['ds-value', 'ds-cases'] },
  'design-result-library-4': { title: '典型问题库', summary: '典型问题可由设计风险、设计质量和检查评价中的问题清单沉淀形成，当前已有问题类型和管理流程，具体问题条目仍需持续补齐。', keyPoints: ['覆盖进度、质量、变更、合规和成本等风险', '问题应关联原因、影响、措施和验证结果', '当前节点区分已有方法内容与待补齐问题实例'], sourceIds: ['ds-risk', 'ds-quality'], contentStatus: '待核原文' },
  'design-result-library-5': { title: '标准做法库', summary: '建设标准库和管理工具书已提供专业、区域、功能和构造做法的组织基础，可作为标准做法库的主要来源。', keyPoints: ['按产品线、专业、部位和功能组织做法', '记录适用条件、构造要求和依据', '标准做法需要保留原始文件版本与审核状态'], sourceIds: ['ds-standard', 'ds-toolbook'] },
  'design-result-library-6': { title: '项目复盘成果库', summary: '设计复盘面向项目完工或阶段结束后的全过程回顾，当前已登记多个真实项目的复盘入口。', keyPoints: ['复盘对象包括管理过程、设计成果和实施效果', '应从问题中提炼可复用经验和改进动作', '项目页需保留来源文档和适用边界'], sourceIds: ['ds-review'] },
  'design-resource-1': { title: '设计院资源', summary: '设计院资源以合作设计院台账、资质、专项能力、地域和典型业绩为主要内容，为设计招采提供可筛选的供方信息。', keyPoints: ['设计院台账记录分类统计和对接分工', '资源库按资质、专项、项目类型和地域分类', '台账需要按月或按发布周期维护'], sourceIds: ['ds-institute', 'ds-resource'] },
  'design-resource-2': { title: '设计大师与专家资源', summary: '设计资源库已登记外部专家人才库，字段覆盖区域、专业、职称、单位、职务和联系方式，为策划、评审和技术攻关提供专家入口。', keyPoints: ['按专业和项目需求匹配专家', '使用前核实专家信息和授权范围', '专家库属于资源信息，不直接替代评审结论'], sourceIds: ['ds-resource'] },
  'design-materials-1': { title: '规范标准', summary: '建设标准库按产品线、专业、功能和构造要求组织设计标准，能够作为规范标准资料的结构化入口；具体规范原文仍需从来源文件核验。', keyPoints: ['区分企业建设标准与外部规范原文', '记录专业、适用范围和版本', '当前来源为知识提炼页，不能替代规范正文'], sourceIds: ['ds-standard'], contentStatus: '待核原文' },
  'design-materials-2': { title: '标准图集', summary: '当前知识页未发现已独立提取的标准图集正文，建设标准库中的专业构造和交付标准可作为关联入口，具体图集需后续补充。', keyPoints: ['需要记录图集名称、编号、版本和适用范围', '图集引用应保留页码或图号', '当前节点不把建设标准条目冒充标准图集'], sourceIds: ['ds-standard'], contentStatus: '待核原文' },
  'design-materials-3': { title: '标准节点', summary: '当前知识页已沉淀地面、楼面做法和燃烧性能等级等构造颗粒度示例，但尚未形成独立标准节点库。', keyPoints: ['标准节点应绑定专业、部位和构造做法', '记录材料、性能等级和适用条件', '具体节点图纸和编号需要原始资料补齐'], sourceIds: ['ds-standard'], contentStatus: '待核原文' },
  'design-materials-4': { title: '模板表单', summary: '示范文本和管理工具书构成设计管理模板表单的现有入口，用于规范项目文件编制和管理动作记录。', keyPoints: ['模板应标注用途、适用阶段和版本', '表单字段需要与责任、时间和成果关联', '使用前核对模板来源和审核状态'], sourceIds: ['ds-template', 'ds-toolbook'] },
  'design-materials-5': { title: '标准化成果', summary: '管理工具书、建设标准库、方案比选库和设计创效案例库共同构成当前已沉淀的标准化成果体系。', keyPoints: ['按工具、标准、案例和指标分层组织', '成果需要连接到实际项目使用场景', '标准化成果必须保留来源和可复用边界'], sourceIds: ['ds-toolbook', 'ds-standard', 'ds-cases'] },
  'design-materials-6': { title: '参考资料', summary: '参考资料节点用于承接设计管理工具书、产品线案例、资源台账和项目复盘等可辅助决策的资料，不等同于正式制度。', keyPoints: ['明确资料类型和来源层级', '用知识卡片摘要降低查找成本', '涉及业务结论时回查权威原文'], sourceIds: ['ds-toolbook', 'ds-review', 'ds-resource'] },
}

const managementSystemSources: KnowledgeSourceRecord[] = [
  source('dms-01', '制度性文件（知识提炼页）', '制度目录', wiki('设计管理体系/制度性文件.md'), '涵盖内容 / 相关来源', '制度性文件是设计管理体系的核心组成部分，包括设计与技术支持中心建设方案、实施细则、设计支持管理细则等制度文件。'),
  source('dms-02', '法人管项目（知识提炼页）', '管理机制', wiki('设计管理体系/法人管项目.md'), '核心要点 / 五大职责', '"法人管项目"是中建三局及二公司 EPC 项目管理的基本管控模式——以公司法人（后台，主要通过"设计与技术支持中心"）统筹支撑各 EPC 项目的设计管理，区别于项目部各自为战。'),
  source('dms-03', '设计管理检查评价机制（知识提炼页）', '检查评价', wiki('设计管理体系/设计管理检查评价机制.md'), '核心要点 / 项目评价表', '设计管理检查评价机制是"法人管项目"体系下第 5 大模块（共 **47 份**），通过"定期专项检查通报 + 项目级设计管理评价表（100 分制、8 大维度）"量化各 EPC 项目设计管理水平。'),
  source('dms-04', '审计巡查与合规（知识提炼页）', '合规监督', wiki('设计管理体系/审计巡查与合规.md'), '核心要点 / 制度化检查与预警', '分公司设计管理体系建设情况检查每半年开展一次；重点 EPC 项目设计管理流程执行情况每季度检查不少于一次。'),
  source('dms-05', '会议与汇报机制（知识提炼页）', '工作机制', wiki('设计管理体系/会议与汇报机制.md'), '核心要点 / 会议类型', '会议与汇报机制是二公司设计管理部保障设计管理工作推进的例会/汇报制度，包括双月会、设计管理推进会、周报月报、季度检查等，是设计管理体系运行的重要抓手。'),
  source('dms-06', '培训与能力建设（知识提炼页）', '能力建设', wiki('设计管理体系/培训与能力建设.md'), '核心要点 / 四个抓手', '培训与能力建设是二公司设计管理体系中"提升设计管理人员专业能力、沉淀设计管理方法论"的专项工作，包含局级 EPC 课程开发、公司内部设计管理能力提升培训班、技术比武，以及设计序列专业职级体系建设四个抓手。'),
  source('dms-07', '设计管理结果应用（知识提炼页）', '结果应用', wiki('设计管理体系/设计管理结果应用.md'), '核心要点 / 问题→提升闭环', '检查发现问题 → 培训补强 → 下期检查验证，构成 PDCA 闭环。'),
  source('dms-08', 'EPC 项目设计管理评价表（知识提炼页）', '评价工具', wiki('设计管理体系/设计管理检查评价机制.md'), '核心要点 / 项目评价表（100 分制）', '评价表覆盖设计管理架构、设计策划管理、设计计划管理、限额设计管理、设计优化管理、设计质量管理、材料设备选型报审、设计报批报建和设计复盘总结等维度。'),
]

const managementSystemCards: KnowledgeCardRecord[] = [
  card('dmc-01', '制度性文件的组成', '制度性文件构成设计管理体系的制度基础，当前知识页列出了建设方案、实施细则、设计支持管理细则、能力建设指导意见和绩效实施细则等来源。', ['建设方案与实施细则构成组织运行依据', '设计支持管理细则明确支持边界', '工作计划与管理指南作为关联内容继续展开'], ['dms-01']),
  card('dmc-02', '法人管项目的管理原则', '以公司法人后台统筹支撑项目设计管理，强调以客户为中心、以项目为中心、以创效为目的、以流程为手段。', ['设计管理监督、评审、进度和培训由后台统筹', '建立建设标准库、设计知识库和技术知识库', '通过界面协同连接公司中心、分公司和项目部'], ['dms-02']),
  card('dmc-03', '检查评价与量化考核', '设计管理检查评价机制通过定期检查通报和项目级评价表，形成综合得分、问题清单、排名和帮扶计划。', ['评价表按 100 分制组织', '覆盖策划、计划、限额、优化、质量和复盘等管理环节', '检查结果用于识别短板和后续提升'], ['dms-03', 'dms-08']),
  card('dmc-04', '审计巡查与预警', '企业内部检查与上级巡查共同构成设计管理监督保障，重点关注流程执行、概算评审、评审意见落实等事项。', ['分公司体系建设检查每半年开展一次', '重点 EPC 项目流程执行每季度检查不少于一次', '出现流程或评审风险时形成预警提示'], ['dms-04']),
  card('dmc-05', '会议与汇报制度', '通过双月会、推进会、周报月报和季度检查等例会与汇报机制，保障设计管理事项持续推进。', ['双月会承担局或公司层面的管理沟通', '推进会服务项目和部门层面的过程推进', '周报月报提供常态化进展反馈'], ['dms-05']),
  card('dmc-06', '培训与能力建设', '能力建设以课程、培训班、技术比武和专业职级体系为抓手，形成知识标准化、能力提升和成果检验的组合机制。', ['课程覆盖 EPC 管理和多专业设计管理', '培训班包含宣贯、专业课程与考试', '专业职级体系支撑人才选用育留'], ['dms-06']),
  card('dmc-07', '检查结果的闭环应用', '检查结果不止用于排名，还要转化为分公司考核、培训补强和下期检查验证的管理动作。', ['检查结果与分公司考核挂钩', '问题转化为培训和帮扶输入', '下一期检查验证提升效果'], ['dms-07']),
]

const managementSystemCases: KnowledgeCaseRecord[] = [
  { id: 'dmc-case-01', name: '丽水医院项目评价实例', scenario: '知识页记录该项目在 2024 年 7 月评价中综合得分 61.5 分，并指出职责分工、周工作计划、设计创效和复盘质量存在短板。', outcome: '可作为检查评价如何识别具体项目管理短板的案例入口。', sourceIds: ['dms-03'] },
  { id: 'dmc-case-02', name: '铁投·书香林语检查排名实例', scenario: '知识页记录该项目在公司专项检查中综合得分 97 分，列入排名前列项目。', outcome: '可作为检查结果形成排名和通报表扬的实例入口。', sourceIds: ['dms-03', 'dms-07'] },
  { id: 'dmc-case-03', name: '仁和净水厂检查排名实例', scenario: '知识页记录该项目在公司专项检查中综合得分 96.5 分，列入排名前列项目。', outcome: '可作为企业检查评价结果应用的实例入口。', sourceIds: ['dms-03', 'dms-07'] },
]

const managementSystemSpace = { overview: '01.01 管理制度的真实内容来自 D:\\设计管理\\wiki\\concepts\\设计管理体系中的知识提炼页。页面展示已提取的制度体系知识，并保留原始 Markdown 路径与章节定位；外部 PDF 原文是否已进入当前知识库，仍以来源状态为准。', managementPoints: ['先区分制度依据、管理机制、检查评价和结果应用，避免把案例或培训资料当成制度条款。', '涉及正式制度条文时，应继续回查原始制度文件，当前知识提炼页不能替代原文审批。', '检查发现的问题应进入培训、帮扶和下一期验证，形成可追踪的管理闭环。'] }

const categoryId = (seedId: string) => `design-${seedId}`
const leafId = (seedId: string, index: number) => `${categoryId(seedId)}-${index + 1}`
const allLeafIds = designManagementCategorySeeds.flatMap(([seedId, , leaves]) => leaves.map((_, index) => leafId(seedId, index)))
const missingDefinitions = allLeafIds.filter((id) => !leafDefinitions[id])
if (missingDefinitions.length) throw new Error(`Missing design content definitions: ${missingDefinitions.join(', ')}`)

const nodeDefinition = (id: string) => {
  if (id === 'design-system-1') return { ...leafDefinitions[id], cards: managementSystemCards, sources: managementSystemSources, cases: managementSystemCases, space: managementSystemSpace }
  const definition = leafDefinitions[id]
  const cards = [card(`card-${id}`, definition.title, definition.summary, definition.keyPoints, definition.sourceIds, definition.contentStatus)]
  const sources = definition.sourceIds.map((sourceId) => sourceCatalog[sourceId] || managementSystemSources.find((item) => item.id === sourceId)).filter((item): item is KnowledgeSourceRecord => Boolean(item))
  return { ...definition, cards, sources, cases: [], space: { overview: definition.summary, managementPoints: definition.managementPoints || definition.keyPoints } }
}

const categoryLeafIds = new Map(designManagementCategorySeeds.map(([seedId, , leaves]) => [categoryId(seedId), leaves.map((_, index) => leafId(seedId, index))]))
const categoryNodes = designManagementCategorySeeds.map(([seedId, name, leaves]) => {
  const id = categoryId(seedId)
  const ids = categoryLeafIds.get(id) || []
  const samples = ids.map(nodeDefinition)
  const sourceCount = new Set(samples.flatMap((sample) => sample.sources.map((item) => item.id))).size
  return [id, {
    id, parentId: 'domain-design', name, type: 'category', description: `${name}的结构化知识、知识卡片和可追溯来源。`, childrenCount: leaves.length,
    knowledgeCount: samples.reduce((sum, sample) => sum + sample.cards.length, 0), sourceCount, coverage: Math.round(samples.filter((sample) => sample.contentStatus !== '待核原文').length / leaves.length * 100),
    tags: ['设计管理', name], relatedTopics: ['epc'], updatedAt: '2026-08-27',
  } as KnowledgeNode] as const
})

const designDomain: KnowledgeNode = {
  id: 'domain-design', name: '设计管理', type: 'domain', description: '覆盖设计管理体系、前期、策划、过程、成果、资源与资料的企业知识体系。',
  childrenCount: categoryNodes.length, knowledgeCount: categoryNodes.reduce((sum, [, node]) => sum + node.knowledgeCount, 0), sourceCount: new Set(allLeafIds.flatMap((id) => nodeDefinition(id).sources.map((item) => item.id))).size,
  coverage: Math.round(categoryNodes.reduce((sum, [, node]) => sum + node.coverage, 0) / categoryNodes.length), tags: ['设计管理', '一级板块'], relatedTopics: ['epc', 'value'], updatedAt: '2026-08-27',
}

const graphByNode: Record<string, KnowledgeNodeSample['graph']> = {}
const samplesByNode: Record<string, KnowledgeNodeSample> = {}
for (const [categoryKey, category] of categoryNodes) {
  for (const id of categoryLeafIds.get(categoryKey) || []) {
    const sample = nodeDefinition(id)
    const node: KnowledgeNode = { id, parentId: category.id, name: designManagementCategorySeeds.flatMap(([, , leaves]) => leaves).find((name) => name === sample.title.replace('制度性文件的组成', '01.01 管理制度')) || id, type: 'knowledge', description: sample.space.overview, childrenCount: 0, knowledgeCount: sample.cards.length, sourceCount: sample.sources.length, coverage: sample.contentStatus === '待核原文' ? 60 : 100, tags: ['设计管理', category.name], relatedTopics: ['epc'], updatedAt: '2026-08-27' }
    if (id === 'design-system-1') node.name = '01.01 管理制度'
    else node.name = designManagementCategorySeeds.flatMap(([, , leaves]) => leaves)[allLeafIds.indexOf(id)]
    const graph = { domain: designDomain, category, node }
    graphByNode[id] = graph
    samplesByNode[id] = { graph, cards: sample.cards, sources: sample.sources, cases: sample.cases, space: sample.space }
  }
}

export const designManagementGraphNodes = [designDomain, ...categoryNodes.map(([, node]) => node), ...Object.values(graphByNode).map((graph) => graph.node)]
export const designManagementSamplesByNode = samplesByNode
