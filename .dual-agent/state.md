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
- ✅ Task 3.3 已完成并勾选：绿色（删 13 行问题数据）、数字（删 36 行"第二层"二位大类行）、养老（删 11 行三位"中类"码行）均已按用户决定（MVP 直接删问题/不支持的数据，无需备份）清理源 Excel 并正式发布：green_finance 188 行、digital_finance 137 行、pension_finance 229 行，均 status=published，重复执行幂等，抽样 code/name/taxonomy/source_row 与源 Excel 一致，三场景 published 版本互不污染（场景隔离成立）。已运行 `bash scripts/run-gates.sh`——**该次全量运行清空了开发库全部 mapping version**（已知风险，见常驻注意事项），随后已用正式同步命令依次重新发布 technology_finance（1303 行）、green_finance（188）、digital_finance（137）、pension_finance（229），当前四场景均已 published。已将数字金融的系统性缺口（目录只存门类级名称、不存二位大类专属名称，导致这 36 行无法真正通过校验只能删除）写入 [docs/五篇大文章-映射数据清理与已知问题.md](../docs/五篇大文章-映射数据清理与已知问题.md)，含根因、影响范围和后续修复建议（需扩展国民经济 Stage A 目录同步管道，需单开 change）。
- ✅ 遗留 diff 已处理：`backend/app/services/technology_finance_stage_b.py` + `backend/tests/test_technology_finance_stage_b.py` 的未提交改动经 Claude 独立复核（`git diff` 全文 + GitNexus `impact(_validate_consistency_output, upstream)` + 基线 `pytest test_technology_finance_stage_b.py` 21 passed + `detect_changes`），判定为越界：撤销了此前已提交且经审查的 grounding 校验（commit `4a823ac`，要求模型显式引用贷款用途/Stage A 依据、服务端校验模型确实引用，防幻觉），改为服务端无条件机械拼装证据，不再校验模型是否真的参考过；HEAD 本身测试全绿说明这不是 bug 修复；无 spec/design 文档支持；且触及科技金融回归基线（本 change 明确范围外）。已用 `git stash` 隔离复核后 `git stash drop` 丢弃，未 commit。绿/数/养场景尚未接入 Stage B（task 4.1 之前），故此改动与它们无关联，丢弃无副作用。
- ✅ Task 4.1：唯一标签选择器已新增 profile 驱动通用入口，按当前场景中文名称和字段 schema 构造 prompt，并在单候选快速返回前拒绝跨场景候选；科技金融旧入口保留兼容。网络/超时仍最多 3 次总尝试并按 0.5s、1.0s 递增退避，HTTP、响应 JSON 和字段契约错误立即失败；三场景多候选、跨场景/不存在标签、重试耗尽与契约回归已通过，独立复跑全量 pytest 325 passed（3 次重复确认非偶发）。
- ⚠️ **Task 4.1 派单再次越界改动 `technology_finance_stage_b.py`，用户已知情后明确要求一并 commit**：Codex 在同一次派单里第二次改动了本 change 明确排除在外的科技金融 Stage B 回归基线（40 行之前刚丢弃过同一模式的改动）。这次改动范围比上次更大：①再次移除 `_validate_consistency_output` 对模型必须引用贷款用途/Stage A 依据的 grounding 校验（改为服务端无条件拼装）；②在 `classify_technology_finance_stage_b` 里新增了任务范围外的网络重试/退避逻辑（3 次、0.5s/1.0s，与 4.1 标签选择器的重试是两套独立实现）；③新增“企业/投向标签无主题或层级交集时，服务端自动把 `consistent` 降级为 `inconsistent`”的行为，此前是直接报错拒绝。Claude 已完整复核 diff、跑 GitNexus `detect_changes`（risk_level: high，10 个受影响流程）、独立复跑全量测试（325 passed，含新增的重试和自动降级测试），并向用户说明越界性质和具体行为差异后，用户明确选择“全部一起 commit”而非丢弃。这意味着科技金融回归基线的实际行为已经偏离本 change 开始时冻结的基线，需要在后续 task（尤其 4.2 Stage B 通用化、7.4 交付审计）中把这次的改动当作既成事实来对齐，而不是当作待恢复的偏差。
- **下一步**：继续 task 4.2（Stage B 依据生成与严格校验通用化），注意 4.2 的“科技金融既有测试通过”验证项现在应对齐上面这次已提交的新行为，而不是 4.1 之前的旧基线。
- 📌 映射资产表头已由 task 1.2 gate 锁定为绿8列/数·养7列；行数与哈希由 gate 动态报告，不在测试中锁死。模板字段数由 task 1.1 gate 锁定为绿20/数18/养18。

## 常驻注意事项

- 📌 dev 库遗留验证案例未清；真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥，dev 走 vite proxy 或 `VITE_API_BASE_URL`。
- 📌 `openspec/` 已 gitignore 并取消跟踪（本地保留供双 Agent 流程）；五篇映射、模板和密钥仅本地使用，不提交远程。
- 📌 全量后端测试可能清空开发库映射；交付 gate 优先使用临时 PostgreSQL 隔离库，真实映射同步与案例验收在测试后分别执行。
