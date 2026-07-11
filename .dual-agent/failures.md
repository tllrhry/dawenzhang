# 评审失误账本 — 只记真实复现过的

> **规则从这里长，不从想象长。** 协议（`core.md`/`loop.md`）只放纯动作清单；潜在风险不预先堆进协议。
> 某类失误**真实复现**才记到这里；复现 ≥2 次再升级为 `AGENTS.md` 硬规则 / 派单模板补丁 / 自动 gate。
> 没复现过的"我担心会出问题"——不进本文件，也不进协议。

## 跨项目通用工作流教训（种子，从 ai_tag_fix 双 Agent 实践带入）

> 这几条不是本项目复现出来的，而是双 Agent 工作流本身在别处已 ≥1 次踩实的坑，属于「机制自带」的已知教训，先摆在这防止新项目重犯。本项目若再复现，把它从「种子」升级为带本项目来源的正式条目。

- **codex 派单不带 yolo 参数 → 干活时因等审批永久挂死**：`mcp__codex-pro__codex` 派实现任务时，codex 执行 shell/写文件会向客户端发「审批请求」，Claude Code 内置客户端不应答 → codex 永久挂住（工具转圈十几分钟、零输出、git 全程干净）。只读/ping 任务不触发审批故秒回，会掩盖问题。对策：每次首轮 `codex()` 必带 `approval-policy:"never"` + `sandbox:"danger-full-access"`；`codex-reply()` 同会话继承可不重复传。
- **别传 `config` 覆盖参数**：派单传 config 覆盖会 `-32000 Connection closed` 挂死；调模型用 `model` 参数，不要用 config。
- **别把重测试塞进派单**：`mvn clean test` / 全量测试（几分钟且工具不显进度）塞进派单易误判挂死。派单只做改动 + 轻量增量自检；重测试 Claude 自己在 Bash 后台跑。
- **派单前别通读实现正文，双倍算力浪费**：检索阶段只用 GitNexus/`rg` 定位符号/文件/影响面写进 spec，不 `Read` 通读正文——Codex 拿到 spec 后必然自己再读一遍。`Read` 主要留给评审阶段看 diff。
- **每 phase 即 commit；长期分支用独立 worktree**：未提交的改动会被用户日常的分支切换（pre-switch hook 自动 `git stash`）连带 stash 掉，事后只查 `git status`（干净）易误判成「Codex 幻觉完成、一行没落盘」。对策：①每完成一个 phase/task 立即 commit，不攒着继续派；②长时间/多阶段功能分支用 `git worktree` 隔离。排查未落盘先查 `git stash list`。
- **测试断言可能过期于 spec，别当「已确认正确」喂给 Codex**：引用既有测试/脚本断言作为前提前，先核对它是否与相关 `spec.md` 一致——测试可能因架构迁移未同步更新而过期。派单要求 Codex 发现断言与 spec 冲突时以 spec 为准并上报，不为让旧测试通过而违反 spec。

## 观察中（出现过，盯是否复现）

- **codex-pro 派单收到 `-32000 Connection closed` 不能默认当作「没干活」**：2026-07-11 在 `align-national-economy-classification-rules-and-result-layout` 1.1/1.2 派单中三次复现——`mcp__codex-pro__codex`/`codex-reply` 报错返回，但 `git status`/`git diff` 核实后发现 codex-pro（本机常驻 app，非纯 stdio 子进程）已经把改动真实写完，其中一次甚至全部测试已通过。用 `/usr/bin/log show`（注意 `log` 是 zsh 内建命令，会跟系统 `log` 冲突，需走全路径）核对同一时间窗口，发现 `codex`/`Codex` 进程对外 443 连接反复在建立后 ~0.1-0.2s 内被 RST（`so_error=54`），几秒到十几秒重试一次——是本机网络对 codex 后端连接不稳定，不是 MCP 工具调用超时配置问题。对策：①收到 `-32000` 后先 `git status`/`git diff` 核实是否已落盘，再决定是否重新派单；②不要看到报错就立刻重派，可能造成重复劳动或和仍在跑的会话产生冲突写入；③已将 `MCP_TOOL_TIMEOUT` 设为全局 `~/.claude/settings.json` 3600000（1 小时）兜底给更多完成时间，但这只是保险不是根因修复。

## 脚本化候选（揣兜里，先不写）

_（本项目暂无）_
