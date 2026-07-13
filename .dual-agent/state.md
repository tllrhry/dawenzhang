# 双 Agent 当前状态

> 这是 Claude 与 Codex 的共享接力页，**只装当前 OpenSpec change 的快照**。已 commit 的任务明细归 `loop-log.md`（只写归档，会话加载时禁读）；常驻项目事实见 `CLAUDE.md` 最小常驻事实段，此处不重复。
> **清空规则**：当前 change 全部 task 勾选完成并收尾后，把「当前 change / 阶段与下一步」两节清空（回到只剩快照头 + 常驻注意事项的空壳），下一个 change 起草时再填。

## 快照

- 更新时间：2026-07-13 · 更新 Agent：Claude · 协议：`.dual-agent/core.md` + `.dual-agent/loop.md`
- Codex 入口：`codex-pro` MCP（Pro，CODEX_HOME=`~/.codex-pro`，默认 `model: gpt-5.6-sol`）。稳定连通命令：`~/Applications/codex-pro.app/Contents/Resources/codex -m gpt-5.6-sol -c model_reasoning_effort=medium mcp-server`。默认 `codex` MCP=Plus 仅备用。

## 当前 change：`add-five-major-articles-green-digital-pension-finance`

- **目标**：在“五篇大文章”父入口下，一次交付绿色金融、数字金融、养老金融三个彼此独立的子场景；各自拥有独立模板、schema、映射版本、案例、结果、历史、session 和导出，但共享科技金融已验证的两阶段实现。
- **范围边界**：科技金融保持既有可用行为并作为回归基线；普惠金融业务逻辑不同，继续 `coming_soon`；不修改国民经济 Stage A 规则，不做跨场景合并判定或映射兜底，不引入五篇向量库/LangChain/LangGraph。
- **映射资产**：最新绿色金融 Excel 已格式化为标准 8 列；数字、养老为标准 7 列；三者均含主题、第一至第四层、NEIC_Code/NEIC_Name，绿色额外有“属于类别”。按 `scenario_id` 分别同步、校验、发布和查询。
- **模板 schema**：绿色 20 字段、数字 18 字段、养老 18 字段；养老的“项目建设 / 运营内容”和“核心交易品类 / 服务内容”已恢复为独立行，三个模板均通过 DOCX 资产 gate。
- **复用契约**：Stage A 独立提交并保存 `stage_a_result_id`；Stage B 只查当前场景映射，正常未命中为当前场景 `not_applicable`，数据/证据异常为 `needs_review`；唯一标签、映射证据和三态一致性口径沿用科技金融。
- **规划状态**：proposal、design、5 份 capability specs、tasks 均已完成；`openspec validate add-five-major-articles-green-digital-pension-finance --strict` PASS；共 22 个实现 task。

## 当前阶段与下一步

- ✅ 按需读取三个最新映射表与三个 Word 模板，确认场景资产结构和字段差异。
- ✅ 创建 OpenSpec change：`add-five-major-articles-green-digital-pension-finance`。
- ✅ 完成 `proposal.md`：冻结“三个独立场景、一次交付、共享实现、普惠范围外”。
- ✅ 完成 `design.md`：定义场景 profile、显式 schema、通用映射、通用 Stage B、数据隔离、API/前端/导出和迁移回滚方案。
- ✅ 完成 5 份 capability specs：profile、mapping、classification、presentation、business-scenario-entry。
- ✅ 完成 `tasks.md`：22 个 task，按资产 → profile/摄取 → 映射 → Stage B → API/导出 → 前端 → 三场景真实闭环排序。
- ✅ OpenSpec strict validation PASS，change 已 apply-ready。
- ✅ Claude 独立复审规划通过：字段算术自洽（绿20/数18/养18）、负例覆盖齐全、strict PASS；唯一的跨 change 归档顺序风险已写入 design.md Open Questions。
- ✅ `add-five-major-articles-technology-finance` 已验收归档；本 change 现为唯一待做 change，归档顺序前置约束已满足。
- ✅ Task 1.1：养老模板已将“项目建设/运营内容”“核心交易品类/服务内容”恢复为独立字段行；绿20/数18/养18 DOCX 资产预检及缺失、重复、嵌入提示负例已建立，统一 runner PASS。LibreOffice 本机缺失，DOCX 已完成结构校验但未完成 PNG 视觉渲染。
- ✅ Task 1.2：建立三场景映射 Excel 资产预检，统一归一中英换行表头，校验必需列、归一后重复列和可选场景类别；忽略锁文件/`.DS_Store`，报告源 SHA-256 与动态数据行数。正式资产预检为绿 201、数 173、养 240 行，定向 7 tests 与统一 runner PASS。
- ✅ Task 1.3：三个新场景已注册稳定 schema（绿20/数18/养18）、Stage A 13 字段子集、模板别名与完整 Stage B 证据白名单/优先级；场景仍保持 `coming_soon`，提示列不进入 schema。
- ✅ Task 2.1：`config.py` 已按既有 pydantic-settings 模式新增绿色、数字、养老模板与映射路径；三个场景 profile 可分别解析模板、映射、schema、显示名与导出名，并注册两阶段工作流元数据但继续保持 `coming_soon`；普惠无工作流和资产路径，未知场景不注册。
- ✅ Task 2.2：科技金融 Word 解析与案例创建已抽取为 profile 驱动的通用五篇摄取器；绿色、数字、养老正式三列表格可按各自 schema 摄取，第三列提示不入库，缺失/重复/无法识别均在写库前失败；科技金融原段落与三列表格入口保留兼容包装。
- ✅ Task 2.3：通用场景案例上传与详情已按 workflow 注册处理器分派；可执行 profile 使用当前场景 schema 完整摄取并返回案例输入，unknown/coming_soon 在处理器与摄取前拒绝，scenario/case 错配在详情处理器前拒绝；四场景契约、普惠/未知负例、错配和国民经济旧端点回归通过，三个新场景生产状态仍保持 `coming_soon`。
- ✅ Task 3.1：科技金融映射同步器已抽取为 profile 驱动的通用五篇映射同步器；通用命令按 `scenario_id` 解析 profile 与资产路径，科技金融旧命令保留兼容。源哈希幂等、2/4 位规范化、同粒度目录校验、完全重复、invalid 报告和原子发布保持不变；绿色、数字、养老各覆盖有效发布、同源复用、代码不存在、名称冲突、完全重复和类别错配，科技金融同步回归通过。
- ✅ Task 3.2：映射标签、查询结果与查询入口已通用化为 `FiveArticles*`，通用入口强制显式接收 `scenario_id`，科技金融旧名保留兼容；查询只选择当前场景最新 published 版本并同时约束版本/行场景，既有显式 4/2 位、完整路径去重、同主题祖先剔除、not_applicable/needs_review 语义保持不变。四场景命中、同 code 跨场景不命中/不兜底及 Stage B 同场景一致性 gate 已建立，定向 58 tests 与统一 runner PASS。
- ⛔ Task 3.3 阻塞（分场景进展不一致，未勾选）：
  - ✅ 绿色：19 条问题（源行 15/108/150/153/157/165 名称冲突、55/57/59/61/63/65/67 的 `2816` 目录不存在及完全重复）已按用户决定（MVP 直接删问题行，无需备份）删除对应 13 行；重新预检 188 行，正式同步命令发布成功：version=2，status=published，source_hash=`0a06f97c6a77bb5f48dc9528aa5a994dbd078cdd909c4b3074989f49873dc0f0`。
  - ⛔ 数字：预检 173 行 PASS，但正式同步 exit 1，退回 `invalid` version（36 条 `name_mismatch`，源行 131-174，均为"第二层"二位大类行）。根因非数据错误：这 36 行写的是 GB/T4754 真实二位大类专属名称（如"01 农业"），但 `national_economy_industry_chunk` 目录只按"门类"（单字母大类，如"农、林、牧、渔业"）存名称，从未采集过二位大类专属名称；科技金融现有 1303 行映射 100% 是四位码，从未触发过这条校验路径，因此这是首次暴露的目录数据缺口而非数字金融 Excel 的格式问题。真正修复需扩展国民经济目录同步管道（`national_economy_catalog_sync` / `NationalEconomyIndustryChunk`，可能需新 Alembic 迁移）以采集真实二位大类名称——这属于 Stage A 基础设施，本 change 设计已明确列为范围外。用户决定暂停在此，本 change 暂不处理数字金融的这 36 行删除或目录扩展。
  - ⛔ 养老：预检 240 行 PASS，正式同步 exit 1，退回 `invalid` version（11 条 `invalid_code`，源行 66/84/89/99/108/120/126/132/136/138/163，均为三位"中类"码如 786/834/195）。当前映射 schema 只支持二位/四位粒度，不支持三位；用户已确认这 11 行按 MVP 直接删除，但因数字金融问题先浮现，**尚未执行**养老的删除操作（养老金融.xlsx 目前未改动，仍是 240 行、source_hash=`80e8558d9b424485ef64356536c7fcf0200d5cab5cf04e78fd04da362db2e03e`）。
  - 场景隔离约束已验证成立：绿色的编辑/发布未触碰数字、养老任何数据；数字、养老两次失败同步均只产生各自的 invalid 版本，互不影响。
- ⏭️ 下一步（用户已要求暂停，等待后续指示）：
  1. 养老：执行已确认的删除（11 行三位码），重新预检+正式同步，核对 published。
  2. 数字：需要用户/业务决定——是发起新 OpenSpec change 扩展国民经济目录以支持二位大类专属名称校验，还是接受先删除这 36 行（数字经济核心产业整个主题）发布 MVP、后续再补。在决定前不要改动 `五篇大文章映射/数字金融.xlsx`。
  3. 全部三场景 published 后，再核对 validation report、published 行数、source_hash 和场景隔离，勾选 task 3.3。
  4. 不要绕过校验或直接修改数据库状态；不要在未获用户确认前删除/修改任一场景映射 Excel。
- 📌 映射资产表头已由 task 1.2 gate 锁定为绿8列/数·养7列；行数与哈希由 gate 动态报告，不在测试中锁死。模板字段数由 task 1.1 gate 锁定为绿20/数18/养18。

## 常驻注意事项

- 📌 dev 库遗留验证案例未清；真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥，dev 走 vite proxy 或 `VITE_API_BASE_URL`。
- 📌 `openspec/` 已 gitignore 并取消跟踪（本地保留供双 Agent 流程）；五篇映射、模板和密钥仅本地使用，不提交远程。
- 📌 全量后端测试可能清空开发库映射；交付 gate 优先使用临时 PostgreSQL 隔离库，真实映射同步与案例验收在测试后分别执行。
