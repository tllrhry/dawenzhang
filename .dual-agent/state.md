# 双 Agent 当前状态

> 这是 Claude 与 Codex 的共享接力页，**只装当前 OpenSpec change 的快照**。已 commit 的任务明细归 `loop-log.md`（只写归档，会话加载时禁读）；常驻项目事实见 `CLAUDE.md` 最小常驻事实段，此处不重复。
> **清空规则**：当前 change 全部 task 勾选完成并收尾后，把「当前 change / 阶段与下一步」两节清空（回到只剩快照头 + 常驻注意事项的空壳），下一个 change 起草时再填。

## 快照

- 更新时间：2026-07-13 · 更新 Agent：Codex · 协议：`.dual-agent/core.md` + `.dual-agent/loop.md`
- Codex 入口：`codex-pro` MCP（Pro，CODEX_HOME=`~/.codex-pro`，默认 `model: gpt-5.6-sol`）。稳定连通命令：`~/Applications/codex-pro.app/Contents/Resources/codex -m gpt-5.6-sol -c model_reasoning_effort=medium mcp-server`。默认 `codex` MCP=Plus 仅备用。

## 当前 change：`add-five-major-articles-technology-finance`

- **目标**：五篇大文章先落地科技金融闭环。上传科技金融 Word 后先独立完成 Stage A 国民经济分类，再以科技金融 Excel 的 code/name 关系做确定性多标签映射，生成结构化匹配依据，并展示“贷款对应的五篇大文章类别与企业类别是否一致”的三态判断。
- **关键边界**：Stage A 不改逻辑且独立提交；Stage B 绑定 `stage_a_result_id` 独立重试。首期只用现有科技金融模板与科技金融映射，不改其他四篇资产、不引入五篇映射向量库、不开放其他场景。
- **映射口径**：同步时以国民经济目录校验同粒度 code/name；运行时查询 Excel 显式四位行及显式二位大类行，保留全部合法候选的 mapping version/source row，并按「同主题最具体者优先」剔除同主题祖先大类标签；多个独立主题候选最终只输出唯一最匹配标签。正常未命中按 `not_applicable=不属于科技金融`，数据冲突/证据不足才 needs_review。
- **一致性**：`consistent / inconsistent / needs_review`，不得因两码不同或有研发资质直接下结论；匹配依据与一致性均保存映射证据、业务字段 key/标签/原文摘录。
- OpenSpec 已完成业务评审修订并通过 strict validation；实现已完成 task 1.1、1.2、2.1、2.2、2.3、3.1、3.2、3.3、4.1、4.2、5.1、5.2。

## 当前阶段与下一步

- ✅ 需求、源文件小样本与现有事务边界已评审；OpenSpec proposal/design/specs/tasks 已按评审结论收敛为科技金融首期。
- ✅ Task 1.1：新增 `technology_finance` 场景注册与 20 字段 schema（Stage A 既有 13 字段 + 科技金融附加 7 字段），模板路径只经 `Settings.technology_finance_template_path` 读取；现有模板两处 Stage A 标签差异登记为别名。
- ✅ Task 1.2：科技金融 Word 摄取兼容现有段落模板和三列表格；缺失、重复、无法识别标签返回 422 且不建案例；科技金融案例详情按注册 schema 返回完整 20 字段。
- ✅ Task 2.1：新增科技金融映射版本/行模型与 0007 Alembic 迁移；数据库约束覆盖 draft/published/invalid、源哈希幂等、2/4 位粒度、查询索引和级联 FK，并完成 downgrade/upgrade 往返。
- ✅ Task 2.2：新增科技金融映射同步服务与命令；双语表头按中文首行匹配，规范化 2/4 位 code/name/tier，以当前模型+维度最新目录版本的 DISTINCT chunks 做同粒度双字段校验；完全重复或数据冲突保留 invalid 报告且不写正式行，全通过在同一事务 draft→published，同源哈希复用。
- ✅ Task 2.3：新增科技金融确定性映射查询；scenario 下选择最大 version 的 published 版本，企业/投向两侧分别只查显式 4 位和显式 2 位行，按完整 taxonomy+code 检查唯一性，并按同主题路径前缀剔除祖先大类；正常投向零命中为 not_applicable，版本报告、行数、code/name、重复键等异常为 needs_review。
- ✅ Task 3.1：新增 `five_articles_results` 模型与 0008 迁移；字段覆盖版本/状态/`stage_a_result_id`/`mapping_version_id`/两侧 code+name 快照/labels+证据/一致性三态+not_applicable/model_output/error_detail；status 与 consistency_status 双 CHECK、`(case_id,version)` 唯一、`(case_id,stage_a_result_id) WHERE status='completed'` 部分唯一索引防重复 completed、三 FK（case/stage_a/ mapping_version），downgrade/upgrade 往返通过。（Codex 会话中途 MCP 断开，Claude 独立复跑迁移+测试+runner 并补收尾）
- ✅ Task 3.2：新增受限 Stage B 判定单元；DeepSeek 仅接收科技金融字段、指定 Stage A 与确定性双侧标签，逐投向标签严格校验标签集合、映射版本/source_row/code/name/path、中文依据和真实原文摘录；两码不同时校验三态矩阵与证据完整性，同码由服务端确定 consistent；违约抛专用错误供 3.3 落 classification_failed。
- ✅ Task 3.3：新增科技金融两阶段编排；首次分类沿用 `classify_case` 的独立提交，普通重试复用最新 `stage_a_result_id`，异议沿用 `reclassify_case` 生成新 Stage A；Stage B 独立提交，失败先 rollback 再写 classification_failed，未完成 Stage A 短路，not_applicable/needs_review 零模型调用，completed 幂等复用。
- ✅ 验证：task 3.3 定向 6 passed（Stage B 失败保留 Stage A、重试不增加 Stage A 版本、异议双版本 +1、completed 幂等、未完成短路、not_applicable/needs_review 零模型调用）；后端全量 208 passed；统一 runner 后端/前端均 PASS。
- ✅ Task 4.1：用 `{scenario_id}` 替换 1.2 遗留的科技金融硬编码上传/详情路由，补齐模板、分类、异议、历史、导出共七类端点；注册科技金融 available 与涉农/绿色/普惠/养老/数字 coming_soon，统一拒绝未知、未开放和 scenario/case 错配；分类响应分离 stage_a/stage_b，历史关联 stage_a_result_id；4.1 导出复用既有三工作表且案例输入按注册 schema 输出，不前移 4.2 科技金融判定工作表。
- ✅ 验证：科技金融 API + 国民经济回归定向 35 passed；后端全量 221 passed；`git diff --check`、Python compileall、统一 runner（BackendPytest/FrontendTypecheck）与 OpenSpec strict validation 均 PASS。GitNexus detect_changes 因同文件路由行位移及用户既有 AGENTS/CLAUDE 改动保守报 HIGH，实际 diff 与回归测试确认旧国民经济处理器内容未变。
- ✅ Task 4.2：科技金融场景导出保留案例输入/当前结论/判定历史并新增“科技金融判定”；正式结果按最新 Stage B 逐标签输出完整层级、code/name、source_row、匹配依据、业务证据摘要和固定名称一致性四态；not_applicable/needs_review/classification_failed 输出中文状态、Stage A 关联/快照和一致性不适用说明，不伪造标签。4.1 的 stage_a/stage_b 响应与历史 stage_a_result_id 契约保持不变。
- ✅ 验证：导出/API/国民经济回归定向 22 passed；后端全量 228 passed；`git diff --check`、Python compileall、统一 runner（BackendPytest/FrontendTypecheck）与 OpenSpec strict validation 均 PASS；工作簿读回覆盖多标签、四层、源行、业务证据、三态一致性、三类无标签状态和最新 Stage A 关联。GitNexus `detect_changes` 因整文件新增 helper 的行位移、路由下方符号位移及用户既有 AGENTS/CLAUDE 改动保守报 HIGH；实际 diff 只改通用场景导出数据装配和 workbook 新增分支，旧国民经济 helper 内容未变且回归通过。
- ✅ 当前科技金融映射资产已修正：`2026-07-13` 重新预检 `五篇大文章映射/科技金融.xlsx`，1303 行全部规范化且目录校验错误为 0，旧的“13 行三位 code”记录已过时。
- ✅ Task 4.2 已 commit `6e87ccf`（终审：Claude 独立复审 diff + 复跑 gates 228 passed + strict validation PASS；AGENTS/CLAUDE 仅符号计数刷新未提交）。
- ✅ Task 5.1：前端场景/API 已参数化；国民经济继续走旧端点，科技金融完整携带 scenario/case 访问模板、上传、详情、分类、异议、历史和导出；场景独立 session key，并在前端再次拒绝案例场景错配，其他四篇与涉农无执行入口。
- ✅ Task 5.2：科技金融结果页按 Stage A/Stage B 分区；逐标签展示主题、四层可空路径、code/name、映射版本/源行、匹配依据和证据摘要；一致性固定显示一致/不一致/待人工复核/不适用，not_applicable/needs_review/classification_failed 均显示中文原因。
- ✅ 验证：前端场景契约测试 3 passed；`npm test`、`npx tsc --noEmit`、`npm run build`、`git diff --check` PASS（Vite 仅保留既有大 chunk 警告）。
- ✅ Task 6.2 联调缺陷修复：投向侧多候选先选出唯一最匹配标签；Stage B 模型改为只返回 `label_basis` 与业务证据，服务端组装 taxonomy/code/name/版本/源行/mapping 证据；旧 `labels` 形态偶发多输出时也只采纳已选标签，不再因数量漂移失败或保存额外标签。
- ✅ Task 6.2 增量验证：Stage B/工作流/选择器定向 31 passed；案例 1540 真实 DeepSeek 只读连跑 3 次，每次均返回 `label_basis`、服务端仅组装源行 410 的 1 个正式标签与 1 条 mapping 证据，未写数据库。
- ✅ Task 6.2 全量验证：数据库恢复 Alembic head 后串行执行统一 runner，BackendPytest/FrontendTypecheck 均 PASS；OpenSpec strict、`git diff --check`、后端健康（PostgreSQL/pgvector/DeepSeek 已配置）和前端 5173 均 PASS。
- ✅ 联调数据恢复：全量测试清空发布版本后，已用正式同步命令恢复科技金融 mapping version 1（DB id 36，1303/1303 行 published）。案例 1646 复用 Stage A #1597 重试成功，Stage B completed，最终仅输出源行 410、主题“战略性新兴产业”的 3973 标签。
- ✅ Task 6.3：唯一标签 DeepSeek 调用对 `httpx.TimeoutException` / `httpx.NetworkError` 最多重试 3 次，前两次分别退避 0.5 秒、1 秒；HTTP 状态和模型契约错误立即失败。模型返回真实但超过 160 字的业务摘录时，先用完整文本做原文落地校验，再由服务端截断保存，伪造摘录仍拒绝。
- ✅ Task 6.3 增量验证：Stage B/唯一标签选择/工作流定向 33 passed；真实案例 1647 复用 Stage A #1598 重试成功，Stage B version 3 completed，mapping version 36，唯一标签为源行 410“战略性新兴产业”，`error_detail=null`。
- ✅ Task 6.3 交付验证：为避免全量测试再次清空开发库映射，创建临时 PostgreSQL 库迁移至 Alembic head 后运行统一 runner，BackendPytest/FrontendTypecheck 均 PASS，随后删除临时库；`git diff --check` 与 OpenSpec strict validation PASS。GitNexus `detect_changes` 因 6.2/6.3 累积未提交实现和 AGENTS/CLAUDE 行位移保守报 HIGH，实际命中科技金融分类、异议与 Stage B 校验流程，已由全量 runner、定向回归和真实案例覆盖。
- ✅ Task 6.4：唯一标签 `label_basis` 的业务证据改为逐条严格校验，模型额外输出的不存在字段、错误标签或非原文摘录不进入正式结果；只要仍有至少一条有效业务证据就继续判定，全部无效仍失败。Stage B/唯一标签选择/工作流定向 35 passed；真实案例 1665 复用 Stage A #1618 重试成功，Stage B version 2 completed，mapping version 36，唯一标签源行 410，保存 3 条有效业务证据，`error_detail=null`。
- ✅ Task 6.4 交付验证：临时 PostgreSQL 隔离库迁移至 head 后统一 runner 的 BackendPytest/FrontendTypecheck 均 PASS，随后删除临时库；OpenSpec strict 与 `git diff --check` PASS。GitNexus 对 6.2-6.4 累计未提交变更保守报 HIGH，命中科技金融分类、异议和 Stage B 校验流程，新增 6.4 符号自身影响分析为 LOW（1 个直接调用方）。
- ⏭️ 下一步：用户刷新前台案例 1665，验收 Stage B 只展示一个最匹配标签；当前 change 的功能 task 已完成，可在用户验收后归档。
- 📦 上一个 `refine-national-economy-loan-direction-evidence-fusion` 已完成并 commit（`dbfe164`/`bfdfaec`/`547f13e`），仍待用户验收后归档；`4278367..547f13e` 尚未 push origin/main。

## 常驻注意事项

- 📌 dev 库遗留验证案例未清（大米/养老等历史连跑残留）；真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥，dev 走 vite proxy 或 `VITE_API_BASE_URL`。
- 📌 `contracts.md` 的 Stage A 独立提交契约已由 task 3.3 测试 gate 化；按场景 schema 展示/导出契约仍待 4.1/4.2 完成。`env-diff.md` 仍空。openspec/ 已 gitignore 并取消跟踪（本地保留供双 Agent 流程）；密钥仅存本地 `.env`，从未上云。
