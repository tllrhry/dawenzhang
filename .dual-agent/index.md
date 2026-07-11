# 双 Agent 渐进检索索引

## 新会话固定顺序

1. 读 `.dual-agent/state.md`：确认当前change、task、完成度和下一步。
2. 读当前 `openspec/changes/<change>/` 的 `proposal.md`、`design.md`、`tasks.md`、命中的 `specs/**/spec.md`。
3. 只按下表加载与任务直接相关的文档；缺少语义时先用 `rg` 定位，再读小节或附近源码/测试。
4. 历史OpenSpec、旧协议和大型运维手册默认不读，只有明确考古/运维时读取。

## 按问题路由

| 问题/任务 | 读取入口 |
|---|---|
| 当前进展、交接、下一步 | `.dual-agent/state.md` |
| 双Agent现行规则 | `.dual-agent/core.md` 与 `.dual-agent/loop.md` |
| 项目总体规划、里程碑 | `项目计划说明.md`、`README.md` |
| 业务需求（五篇大文章/国民经济分类） | `副本五篇大文章需求书0710.docx`、`五篇大文章映射/`、`国民经济/` |
| 后端结构、API、配置 | `backend/app/`（入口 `app/main.py`、配置 `app/core/config.py`） |
| 后端构建/启动/测试 | `Makefile`（`backend-dev`/`test`/`migrate`）、`backend/run.py` |
| 前端结构与构建 | `frontend/`（Vite+React+TS，`package.json` scripts） |
| 数据库迁移 | `backend/alembic/`、`backend/scripts/migrate.sh` |
| GitNexus代码图谱 | `CLAUDE.md` GitNexus 段与 `.claude/skills/gitnexus/` |
| 横切契约与gate | `.dual-agent/contracts.md` |
| 已复现流程失误 | `.dual-agent/failures.md` |
| 环境差异（开发↔部署） | `.dual-agent/env-diff.md` |

## 检索纪律

- 当前OpenSpec定义实现范围；文档解释背景；源码与配置裁决当前运行事实。
- 配置/YAML/SQL/迁移脚本等GitNexus盲区使用定向`rg`和附近文件核对。
- 不把归档change重新解释成当前需求；只有当前change引用时才读取。
- 发现文档与源码冲突时，先在`.dual-agent/state.md`记录，再修正文档或明确归档。
