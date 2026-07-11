<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **dawenzhang** (768 symbols, 1425 relationships, 33 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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

# 双 Agent 工作方式（Codex 侧）

本项目采用 Claude/Codex 双 Agent 工作方式。收到派单后：

1. 先读 `.dual-agent/state.md` 与 `.dual-agent/index.md`，按需读当前 `openspec/changes/<change>/`。当前 OpenSpec 是范围事实源，先指出规格缺口再动手。
2. 修改符号前做上游影响分析；配置/SQL/迁移等盲区文件直接核对；严守范围，保留无关改动。命中 `.dual-agent/contracts.md` 契约时报告，“靠人”即交回。
3. 交付前自跑：增量自检 + 统一 runner `scripts/run-gates.sh` + task 验证命令。结构化交付文件说明、影响、契约、验证摘要、人工判断与下一步；不伪造模型或 token。

## 最小常驻事实

- 后端：FastAPI + SQLAlchemy 2.x + Alembic，Python 3.12，端口 8000，API 前缀 `/api/v1`，DB 仅 SQLite；配置只经 `backend/app/core/config.py`（pydantic-settings）
- 前端：React 19 + Vite 6 + TypeScript 5.7，dev 端口 5173
- 命令：后端测试 `PYTHONPATH=backend python -m pytest backend/tests`；前端 `npm run test`（`tsc --noEmit`）；迁移 `bash backend/scripts/migrate.sh`
