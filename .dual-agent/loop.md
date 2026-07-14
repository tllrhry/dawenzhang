# 半自动 Loop 手册

1. 派单前先按tasks.md标注的批次分组（耦合紧密的相邻task合并为一批，独立的不硬凑，跨域不合并）；批次内每个task须含域与验证；加载state/index、当前change、common与域模板，每phase新会话。
2. `/dispatch`一次性把整批task编号交给同一个Codex session。Codex挑战规格缺口、做影响分析、实现批次内全部task，运行一次增量构建/自检、`scripts/run-gates.sh`、逐task验证；结构化交付文件、影响、契约和摘要（覆盖整批）。
3. Claude终审按批次触发，且以次数最少为目标：命中core.md第6条强制信号（契约/HIGH-CRITICAL/change内首次模式/最终收尾）时，做独立跑runner+审diff/范围/OpenSpec/盲区的完整核验；未命中时用`detect_changes()`+目标diff核验范围即可，可连续攒多个批次再一起终审。人工契约始终交回。
4. 同phase用原thread打回。终审后真实commit（可整批一次commit，或Codex内部按task拆小commit后一次性确认）；成功才勾批次内全部task、更新state（每批一段而非逐task）与loop-log。
5. 失败交回命令、退出码、关键错误、尝试与下一步；不得伪造模型或token。
