# 双 Agent 共同铁律

1. 每次先读`state.md`并按`index.md`检索；当前OpenSpec是范围事实源。
2. Codex负责规格自查、检索、实现、自检；Claude负责对齐、派单、独立终审。
3. 修改符号前做上游影响分析；盲区文件（配置/SQL/YAML/迁移脚本等）直接核对；保留无关改动。
4. Codex调用走`codex-pro` MCP（Pro套餐，CODEX_HOME=`~/.codex-pro`；默认`codex` MCP=Plus仅备用）。首轮显式传项目根cwd、`approval-policy: never`、`sandbox: danger-full-access`、默认`model: gpt-5.6-sol`；不得传config覆盖。
5. 每phase新会话，仅同phase打回续接。Codex跑增量构建/自检、runner、task验证；Claude独立复跑runner。
6. “靠人”契约必须交回。收尾：实现/自检→runner→终审→commit→勾task→更新state/loop-log；commit失败不得打勾。
7. 机械工作归Codex，判断与终审归Claude；Claude不直接修改业务实现。
8. 每两周或change收尾提议独立体检，报告写入audits。

详见[loop.md](loop.md)。
