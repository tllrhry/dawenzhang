<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **dawenzhang** (1866 symbols, 4426 relationships, 120 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/dawenzhang/context` | Codebase overview, check index freshness |
| `gitnexus://repo/dawenzhang/clusters` | All functional areas |
| `gitnexus://repo/dawenzhang/processes` | All execution flows |
| `gitnexus://repo/dawenzhang/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# 双 Agent 工作方式

本项目采用 Claude/Codex 双 Agent 工作方式。共享的当前进展与渐进检索入口在：

- `.dual-agent/state.md`
- `.dual-agent/index.md`

现行协议为 `.dual-agent/core.md` + `.dual-agent/loop.md`。派单走 `/dispatch` skill（`.claude/skills/dispatch/`）+ Codex `codex-pro` MCP。统一 runner 为 `scripts/run-gates.sh`。

## 最小常驻事实

- 后端：FastAPI + SQLAlchemy 2.x + Alembic，Python 3.12，端口 8000，API 前缀 `/api/v1`；DB **仅 PostgreSQL + pgvector**（`config.py` 强制校验，非 postgresql 直接报错；无 SQLite 回退）
- 前端：React 19 + Vite 6 + TypeScript 5.7，dev 端口 5173；`npm run test` 当前 = `tsc --noEmit`（尚无运行时测试框架）
- 配置只经 `backend/app/core/config.py`（pydantic-settings，环境变量/`.env` 优先）；密钥仅存本地 `.env`（gitignore），不得提交
- 一键启动：`./start.sh`（Docker Compose 起 PostgreSQL + 迁移 + 宿主机跑 FastAPI/Vite）
- 常用命令：后端 `PYTHONPATH=backend python backend/run.py`；测试 `PYTHONPATH=backend python -m pytest backend/tests`（单测 `... -k test_name`）；前端 `npm run dev`/`npm run build`/`npm run test`
- 统一验证 runner：`bash scripts/run-gates.sh`（pytest + 前端 `tsc --noEmit`）

详细模块、架构与运行手册不要常驻加载；按 `.dual-agent/index.md` 命中后读取。

## 应用架构（国民经济行业分类闭环）

当前唯一落地功能是「国民经济行业分类」；涉农与五篇大文章仅在 UI 显示"暂未开放"。核心链路（`backend/app/services/national_economy_*.py`，逐层职责单一）：

1. **目录同步** `catalog_sync` → `catalog_chunks`：GB/T 4754 Excel 是行业目录唯一事实源（`NATIONAL_ECONOMY_CATALOG_PATH`，只读挂载不提交），切片 + 硅基流动 embedding 写入 pgvector；幂等键 = 源哈希 + embedding 模型 + 维度。命令 `backend/scripts/sync_national_economy_catalog.py`。
2. **模板摄取** `case_ingestion`：解析单企业 `.docx`（13 固定字段三列表格 + 旧版 `字段：内容` 段落兼容），缺失/重复/无法识别报 422 且不建案例。
3. **判定规则** `decision_policy`：四级证据层优先级（主营营收 > 贸易合同/产业链 > 贷款用途 > 营业执照经营范围），逐级降级取最高可用层，低层冲突记录但不反转，异议并入既有层而非新增第五级。
4. **检索** `retrieval`：按证据层分别 embedding → pgvector cosine Top30 召回 → 硅基流动 rerank Top5–8，产出可追溯 `EvidenceSnapshot`。
5. **分类** `classification`：DeepSeek 受限判定，企业结论与贷款投向结论分别只能从各自候选中选择；笼统用途回落企业结论，超出经营范围或 `no_match` 转人工复核，云端失败明确抛错不臆造。
6. **工作流** `classification_workflow`：首次分类 / 异议重判 / 版本递增（max+1），编排企业和贷款投向双候选；失败 rollback 不覆盖既有 completed。
7. **导出** `case_export`：openpyxl 三工作表（案例输入 / 当前结论 / 判定历史），当前结论与历史均包含贷款投向字段。

REST 入口 `backend/app/api/routes/national_economy.py`（8 端点：场景 / 模板下载 / 上传 / 案例 / 分类 / 异议 / 历史 / Excel 导出）；模型 `backend/app/models/national_economy.py` + 迁移 `alembic/versions/0001` 至 `0005`。前端 `frontend/src/App.tsx` + `api.ts` 单页驱动全流程，dev 经 vite proxy 到 8000。

云端依赖：硅基流动（embedding 4096 维 + rerank）、DeepSeek（最终分类）；分层超时 embedding 30s / DeepSeek 120s / 端到端 180s（nginx+uvicorn 须 ≥ 此值）。同步目录/联调前可跑 `backend/scripts/probe_models.py` 实测三 API。

当前演示服务器使用 `/root/dawenzhang` 源码、`dawenzhang.service` 后端和宿主机 Nginx 静态前端；发布步骤见 `docs/服务器更新.md`。不将服务器地址、账号、密码或 `.env` 内容写入仓库。
