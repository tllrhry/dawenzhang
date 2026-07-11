# 半自动 Loop 手册

1. task须含域与验证；加载state/index、当前change、common与域模板，每phase新会话。
2. Codex挑战规格缺口、做影响分析、实现，并运行增量构建/自检、`scripts/run-gates.sh`、task验证；结构化交付文件、影响、契约和摘要。
3. Claude独立跑runner并审diff、范围、OpenSpec和盲区；人工契约交回。
4. 同phase用原thread打回。终审后真实commit；成功才勾task、更新state与loop-log。
5. 失败交回命令、退出码、关键错误、尝试与下一步；不得伪造模型或token。
