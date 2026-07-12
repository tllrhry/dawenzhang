# 双 Agent 当前状态

> 这是 Claude 与 Codex 的共享接力页，**只装当前 OpenSpec change 的快照**。已 commit 的任务明细归 `loop-log.md`（只写归档，会话加载时禁读）；常驻项目事实见 `CLAUDE.md` 最小常驻事实段，此处不重复。
> **清空规则**：当前 change 全部 task 勾选完成并收尾后，把「当前 change / 阶段与下一步」两节清空（回到只剩快照头 + 常驻注意事项的空壳），下一个 change 起草时再填。

## 快照

- 更新时间：2026-07-12 · 更新 Agent：Claude · 协议：`.dual-agent/core.md` + `.dual-agent/loop.md`
- Codex 入口：`codex-pro` MCP（Pro，CODEX_HOME=`~/.codex-pro`，默认 `model: gpt-5.6-sol`）。稳定连通命令：`~/Applications/codex-pro.app/Contents/Resources/codex -m gpt-5.6-sol -c model_reasoning_effort=medium mcp-server`。默认 `codex` MCP=Plus 仅备用。

## 当前 change：`refine-national-economy-loan-direction-evidence-fusion`

- **目标**：判贷款真实投向。三级优先级 **贷款用途 > 贸易合同 > 授信审批**，**冲突以贸易合同为准**（受托支付下钱直接买合同标的物，反映真实流向）；要求**证据融合 + LLM 仲裁，明确否决布尔式逐级降级**（用途几乎永远可用，严格降级会永远停第一级）。
- **起因**：投向信号原只来自「贷款用途详细描述」——`retrieve_loan_direction_evidence` 只用贷款用途层召回、提示词决策树只围绕用途 vs 主营/经营范围；「贸易合同核心交易品类」第 2 层完全没进投向候选、「授信审批意见」随第 3 层进召回但提示词未当辅助证据用。
- **范围外**：企业轴、一致性标记语义（投向码==企业码字面相等）、死代码 `decide_loan_direction`。
- **3 任务**：1.1 检索追加贸易合同召回并入投向候选 + 放宽跳过条件；2.1 提示词三级融合仲裁 + 贸易合同优先冲突 + 「为主营采购投入不改判」原则 + matching_basis 指明判定证据；3.1 真实闭环（背离样例投向跟随贸易合同 + 授信审批样例 + 养老/大米基准回归）。
- OpenSpec 已起草并通过 `--strict`。

## 当前阶段与下一步

- ✅ **全 3 任务完成并 commit：1.1（`dbfe164`）/2.1（`bfdfaec`）/3.1 fixtures（`547f13e`）**（明细见 loop-log）。**本 change 已收尾，等用户验收后归档**（`openspec/changes/archive/2026-07-12-refine-national-economy-loan-direction-evidence-fusion`）。三单未 push origin/main（`4278367..547f13e` 待推）。
- ✅ **3.1 真实云端闭环（Claude 直接执行，四场景全通过）**：①「用途与贸易合同背离」机床企业服装贸易（案例 704）——用途「补充经营流动资金」笼统，贸易合同核心品类=服装批发→企业 3421 金属切削机床制造（88% 主导锁定+定义命中）、**投向 5132 服装批发（未回落企业结论，融合正确跟随贸易合同真实流向）、matches=false、依据全中文直接指明「据贸易合同判定资金真实流向为服装批发…命中 5132 包括…」、按经销商=批发**；②「授信审批限定投向」（案例 707）——用途「补充流动资金」笼统+贸易合同「无」+授信审批「专款专用只可用于采购服装批发」→投向 5132 服装批发、matches=false、依据指明依据授信审批，**验证 1.1 授信审批跳过放宽（候选池经含授信审批文本的贷款用途层召回出 5132）**；③养老（705）笼统用途→回落 8514 养老服务 matches=true（主导锁定+授信审批佐证属主营，未劣化）；④大米（706）用途收购大米属主营→回落 5121 米面制品及食用油批发 matches=true（definition-grounded 批发未回退零售、演示「为主营采购投入不改判」，未劣化）。Excel 导出（704）三工作表当前结论+判定历史均含贷款投向代码 `F51-F5132 服装批发`+投向依据+一致性「不一致」。全 gates：后端 145 passed、前端 tsc+build PASS、run-gates OVERALL PASS、strict valid。dev 库遗留验证案例 703-707（未清；703 为汽配坏样例已弃、docx 已删）。**初次曾选「汽车零配件批发」作背离 B，实测发现 GB/T 4754 无该四位码（只有 5263 汽车零配件零售、5173 摩托车零配件批发）→改用有干净码的 5132 服装批发重跑；期间证实融合逻辑本身在坏样例上也正确（模型正确跟随贸易合同判服装/汽配批发、正确排除零售），no_match 仅因目标码不存在。**
- 上一个 change `refine-...-basis-code-and-dominant-main-business`（大类-小类显示码 + 主营锁定 + 依据全中文，全 7 任务已 commit）**等用户验收后归档**（`openspec/changes/archive/2026-07-12-...`）。`definition-grounded` change 已全部收尾归档并 push origin/main（`60ab394..4278367`）。

## 常驻注意事项

- 📌 dev 库遗留验证案例未清（大米/养老等历史连跑残留）；真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥，dev 走 vite proxy 或 `VITE_API_BASE_URL`。
- 📌 `contracts.md`/`env-diff.md` 仍空，待真实契约/差异出现再填。openspec/ 已 gitignore 并取消跟踪（本地保留供双 Agent 流程）；密钥仅存本地 `.env`，从未上云。
