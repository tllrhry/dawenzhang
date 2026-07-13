# 横切契约台账 — dawenzhang

> **通用机制（可搬去任何项目）+ 本项目实例表（下方）分开看：**
> - 机制部分（本段 + 末尾「维护规则」）是双 Agent 框架的一部分，换项目照抄结构即可。
> - 表格的**行**是本项目特有的契约，随真实发现逐行填。
>
> **「机器强制点(gate)」那一列才是产品，本表只是索引。**
> 用法：派单/评审时，改动命中「命中触发」列所述场景 → 必须查对应行；
> 状态为「无 gate=挂账」的契约 = 一条可见的待还技术债，评审须走人工全景核对，别误以为机器已覆盖。
>
> **谁跑 gate**：Codex 交付前用统一 runner（`scripts/run-gates.sh`）自检；Claude 侧终审前用同一 runner 独立复核。状态「⏳待建」时 gate 代码仍属实现；「📝靠人」必须交回判断。
>
> 为什么需要它：横切契约天生落在切片之间，无单一 owner；缺失型违反（该加没加）`git diff` 评审看不见。

## 本项目契约表（dawenzhang 特有）

| 契约 | 机器强制点（gate 在哪） | 命中触发（改到这个就查本行） | 状态 |
|---|---|---|---|
| 复用 `national_economy_classification_workflow.classify_case` 的组合工作流必须把 Stage A 视为已独立提交，固定并持久化 `stage_a_result_id`；下游失败不得假设可回滚 Stage A，无异议重试不得重复生成 Stage A 版本 | `backend/tests/test_technology_finance_classification_workflow.py`（Stage B 失败保留 Stage A、重试不增加 Stage A 版本、异议双版本 +1、completed 幂等） | 新增/修改任何复用 `classify_case` 的复合分类工作流 | ✅ |
| 多场景案例详情、前端展示和导出必须按场景注册的字段 schema 枚举字段，不得继续写死国民经济 `FIELD_LABELS` 导致场景附加字段丢失 | `add-five-major-articles-technology-finance` task 1.2/4.1/4.2：待建 API 与导出测试（科技金融全部字段可读/可导出，国民经济回归不变） | 新增场景、修改案例响应、输入展示或案例导出 | ⏳待建 |

## 维护规则
- **新发现一条横切契约**（周期性体检 / 评审中撞见）→ 加一行，状态先标「无 gate=挂账」，再排是否 gate 化。
- **一条契约建成 gate** → 更新「机器强制点」列写清 gate 位置与运行命令、状态改 ✅。
- **一条契约评估后确认机械不可行** → 状态保持「无 gate=挂账」，并在对应 openspec/注释里锁定「靠人 + 台账提醒」的决策，不硬造脆弱测试。
