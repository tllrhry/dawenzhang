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

# 双 Agent 工作方式

本项目采用 Claude/Codex 双 Agent 工作方式。共享的当前进展与渐进检索入口在：

- `.dual-agent/state.md`
- `.dual-agent/index.md`

现行协议为 `.dual-agent/core.md` + `.dual-agent/loop.md`。派单走 `/dispatch` skill（`.claude/skills/dispatch/`）+ Codex `codex-pro` MCP。统一 runner 为 `scripts/run-gates.sh`。

## 最小常驻事实

- 后端：FastAPI + SQLAlchemy 2.x + Alembic，Python 3.12，端口 8000，API 前缀 `/api/v1`，DB 仅 SQLite
- 前端：React 19 + Vite 6 + TypeScript 5.7，dev 端口 5173
- 配置只经 `backend/app/core/config.py`（pydantic-settings，环境变量/`.env` 优先）
- 常用命令：后端 `PYTHONPATH=backend python backend/run.py`；测试 `PYTHONPATH=backend python -m pytest backend/tests`；前端 `npm run dev`/`npm run build`/`npm run test`

详细模块、架构与运行手册不要常驻加载；按 `.dual-agent/index.md` 命中后读取。
