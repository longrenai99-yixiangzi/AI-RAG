# V2.6.1 Gold 来源覆盖审计

- 审计问题数：`20`
- 候选正文已存在：`11`
- 仅登记页/查询页：`3`
- 物理 Gold 存在但未入候选：`6`
- 物理 Gold 未找到：`0`

未入候选的物理 Gold 只登记为待审批，不自动进入运行时。

## V261-LSR-001（Q05）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['建设标准库', '建设标准库.md']`
- 候选匹配：`[{'file_name': '建设标准库.md', 'source_path': 'D:\\设计管理\\wiki\\concepts\\设计支持\\建设标准库.md', 'document_type': 'RETROSPECTIVE', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-002（Q03）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['方案比选库', '方案比选库.md']`
- 候选匹配：`[{'file_name': '方案比选库.md', 'source_path': 'D:\\设计管理\\wiki\\concepts\\设计支持\\方案比选库.md', 'document_type': 'TABLE_LEDGER', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-003（Q06）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['设计策划评审', '设计策划评审.md']`
- 候选匹配：`[{'file_name': '设计策划评审.md', 'source_path': 'D:\\设计管理\\wiki\\concepts\\设计支持\\设计策划评审.md', 'document_type': 'REVIEW_RECORD', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-004（Q07）

- 分类：`REGISTRATION_OR_QUERY_ONLY_IN_CANDIDATE`
- 目标文件：`['设计任务书', '设计任务书汇编', '设计任务书汇编.md']`
- 候选匹配：`[{'file_name': '设计任务书汇编.md', 'source_path': 'D:\\设计管理\\wiki\\sources\\设计任务书汇编.md', 'document_type': 'REGISTER_PAGE', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-005（Q51）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['b6077e3f74f0a1b7ae9f', 'b6077e3f74f0a1b7ae9f.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\b6077e3f74f0a1b7ae9f.md', 'size_bytes': 39181, 'sha256': 'c392bc19e997b52f2f31be948ea8876830c0055f612016fd8b1dc119affcb323'}]`

## V261-LSR-006（Q70）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['cb93c382c9197043cab1', 'cb93c382c9197043cab1.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\cb93c382c9197043cab1.md', 'size_bytes': 44914, 'sha256': '7ce9483b9a83a5a0797c647718e82de2a9e68028a9ffa558c491102d06c29424'}]`

## V261-LSR-007（Q77）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['f80e5def25e5a56bfc6f', 'f80e5def25e5a56bfc6f.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\f80e5def25e5a56bfc6f.md', 'size_bytes': 23307, 'sha256': 'bcc9a3b8685a86085ce26f1b5163406c6db9801a4258778aee98ee912a5ba082'}]`

## V261-LSR-008（Q29）

- 分类：`REGISTRATION_OR_QUERY_ONLY_IN_CANDIDATE`
- 目标文件：`['设计管理策划章节问答', '设计管理策划章节问答.md']`
- 候选匹配：`[{'file_name': '设计管理策划章节问答.md', 'source_path': 'D:\\设计管理\\wiki\\queries\\设计管理策划章节问答.md', 'document_type': 'QUERY_PAGE', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-009（Q08）

- 分类：`REGISTRATION_OR_QUERY_ONLY_IN_CANDIDATE`
- 目标文件：`['法人管项目', '法人管项目资料登记', '法人管项目资料登记.md']`
- 候选匹配：`[{'file_name': '法人管项目资料登记.md', 'source_path': 'D:\\设计管理\\wiki\\sources\\法人管项目资料登记.md', 'document_type': 'REGISTER_PAGE', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-010（Q09）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['法人管项目', '法人管项目.md', '设计与技术支持中心', '设计与技术支持中心.md']`
- 候选匹配：`[{'file_name': '法人管项目.md', 'source_path': 'D:\\设计管理\\wiki\\concepts\\设计管理体系\\法人管项目.md', 'document_type': 'RESPONSIBILITY_CONTRACT', 'parse_status': 'parsed'}, {'file_name': '设计与技术支持中心.md', 'source_path': 'D:\\设计管理\\wiki\\organizations\\设计与技术支持中心.md', 'document_type': 'RESPONSIBILITY_CONTRACT', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-011（Q40）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['0ee2959550610ce23750', '0ee2959550610ce23750.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\0ee2959550610ce23750.md', 'size_bytes': 176301, 'sha256': 'c921b8c3773304cd2ffef8659812d1498317900cbd8892460454b22a6060f89d'}]`

## V261-LSR-012（Q58）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['2c5dbe10c9b44d1d47d0', '2c5dbe10c9b44d1d47d0.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\2c5dbe10c9b44d1d47d0.md', 'size_bytes': 61838, 'sha256': '2d2a1005a60aae43465dd06dcb633bcd2ad1b1f3fd2812a7ee3b063e2b030cdc'}]`

## V261-LSR-013（Q80）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['2024年年度总结', '2024年年度总结.md', '37746aede39d6b33f745', '37746aede39d6b33f745.md']`
- 候选匹配：`[{'file_name': '2024年年度总结.md', 'source_path': 'D:\\设计管理\\raw\\工作总结\\2024年年度总结.md', 'document_type': 'TRAINING', 'parse_status': 'parsed'}]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\37746aede39d6b33f745.md', 'size_bytes': 9620, 'sha256': 'ce10009f6d315357ef504aa491abcf0f2f43e1f1f83eee4bdd1152894984d2f2'}]`

## V261-LSR-014（Q81）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['2024年度总结2', '2024年度总结2.md', 'e0d9ad43a1f66a2d8531', 'e0d9ad43a1f66a2d8531.md']`
- 候选匹配：`[{'file_name': '2024年度总结2.md', 'source_path': 'D:\\设计管理\\raw\\工作总结\\2024年度总结2.md', 'document_type': 'RESPONSIBILITY_CONTRACT', 'parse_status': 'parsed'}]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\e0d9ad43a1f66a2d8531.md', 'size_bytes': 16977, 'sha256': '88548fb5ec49a3ecb5f757bd5d96002ef91e87cc7d7f4c6e5ba8db90ca86fdf6'}]`

## V261-LSR-015（Q86）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['2024年半年总结', '2024年半年总结.md', 'e1f57b2f1862b9e921b2', 'e1f57b2f1862b9e921b2.md']`
- 候选匹配：`[{'file_name': '2024年半年总结.md', 'source_path': 'D:\\设计管理\\raw\\工作总结\\2024年半年总结.md', 'document_type': 'REVIEW_RECORD', 'parse_status': 'parsed'}]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\e1f57b2f1862b9e921b2.md', 'size_bytes': 11183, 'sha256': '6c15697367fd1709ca6cdb352839f366780766c9e99437857c7cbd21c78184fd'}]`

## V261-LSR-016（Q89）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['2025年半年总结', '2025年半年总结.md', '55122ed33fea8877f535', '55122ed33fea8877f535.md']`
- 候选匹配：`[{'file_name': '2025年半年总结.md', 'source_path': 'D:\\设计管理\\raw\\工作总结\\2025年半年总结.md', 'document_type': 'RETROSPECTIVE', 'parse_status': 'parsed'}]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\55122ed33fea8877f535.md', 'size_bytes': 35360, 'sha256': '801c4796a3148a19ecd22ad1ec5e89a1e0568860170a8cee71793573ba30ae13'}]`

## V261-LSR-017（Q95）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['2025年年度总结', '2025年年度总结.md']`
- 候选匹配：`[{'file_name': '2025年年度总结.md', 'source_path': 'D:\\设计管理\\raw\\工作总结\\2025年年度总结.md', 'document_type': 'RESPONSIBILITY_CONTRACT', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-018（Q107）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['铁投·书香林语（华中）', '铁投·书香林语（华中）.md']`
- 候选匹配：`[{'file_name': '铁投·书香林语（华中）.md', 'source_path': 'D:\\设计管理\\wiki\\concepts\\设计管理成果总结\\项目经验总结库\\各项目\\铁投·书香林语（华中）.md', 'document_type': 'RETROSPECTIVE', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-019（Q129）

- 分类：`EXACT_BODY_IN_CANDIDATE`
- 目标文件：`['EPC项目设计管理流程', 'EPC项目设计管理流程.md']`
- 候选匹配：`[{'file_name': 'EPC项目设计管理流程.md', 'source_path': 'D:\\设计管理\\wiki\\topics\\EPC项目设计管理流程.md', 'document_type': 'DESIGN_TASK_BOOK', 'parse_status': 'parsed'}]`
- 物理匹配：`[]`

## V261-LSR-020（Q130）

- 分类：`PHYSICAL_GOLD_NOT_IN_CANDIDATE`
- 目标文件：`['77d7e542b45a93853e16', '77d7e542b45a93853e16.md', '90b557ce19fb9d757b47', '90b557ce19fb9d757b47.md']`
- 候选匹配：`[]`
- 物理匹配：`[{'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\77d7e542b45a93853e16.md', 'size_bytes': 87713, 'sha256': 'c78ccf30fb5e64479fba27a4bdf73b6cbc243b4bc31c8a3f2de1415054d48e7c'}, {'path': 'D:\\设计管理\\.ai-growth\\parsed\\approved-sources\\90b557ce19fb9d757b47.md', 'size_bytes': 14803, 'sha256': 'd23adc39ed9e3fd7c13f41b5cb02a9399f813cc902b2c04a9537853586d2ad9e'}]`
