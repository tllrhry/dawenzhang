# 双 Agent 当前状态

> 这是 Claude 与 Codex 的共享接力页，**只装当前 OpenSpec change 的快照**。已 commit 的任务明细归 `loop-log.md`（只写归档，会话加载时禁读）；常驻项目事实见 `CLAUDE.md` 最小常驻事实段，此处不重复。
> **清空规则**：当前 change 全部 task 勾选完成并收尾后，把「当前 change / 阶段与下一步」两节清空（回到只剩快照头 + 常驻注意事项的空壳），下一个 change 起草时再填。

## 快照

- 更新时间：2026-07-13 · 更新 Agent：Codex · 协议：`.dual-agent/core.md` + `.dual-agent/loop.md`
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
- ⏭️ 下一步：执行 task 2.2，将科技金融 Word 解析与案例创建抽取为按 profile 工作的通用五篇摄取器；修改任何符号前先做 GitNexus upstream impact，HIGH/CRITICAL 先暂停报告。
- 📌 映射资产表头已由 task 1.2 gate 锁定为绿8列/数·养7列；行数与哈希由 gate 动态报告，不在测试中锁死。模板字段数由 task 1.1 gate 锁定为绿20/数18/养18。

## 常驻注意事项

- 📌 dev 库遗留验证案例未清；真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥，dev 走 vite proxy 或 `VITE_API_BASE_URL`。
- 📌 `openspec/` 已 gitignore 并取消跟踪（本地保留供双 Agent 流程）；五篇映射、模板和密钥仅本地使用，不提交远程。
- 📌 全量后端测试可能清空开发库映射；交付 gate 优先使用临时 PostgreSQL 隔离库，真实映射同步与案例验收在测试后分别执行。
