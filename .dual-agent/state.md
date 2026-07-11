# 双 Agent 当前状态

> 这是 Claude 与 Codex 的共享接力页，只保留当前快照。历史圈次写入 `loop-log.md`。

## 快照

- 更新时间：2026-07-11
- 更新 Agent：Claude
- 当前协议：`.dual-agent/core.md` + `.dual-agent/loop.md`
- Codex入口：`codex-pro` MCP（Pro套餐，CODEX_HOME=`~/.codex-pro`），默认`model: gpt-5.6-sol`；默认`codex` MCP=Plus仅备用
- 上一个 change：`implement-national-economy-classification-mvp`（第1–5点全部完成，OpenSpec 19/19，尚未归档，等待用户验收）
- 当前 change：`align-national-economy-classification-rules-and-result-layout`（纠偏判定规则契约与结果页分栏，用户已多轮评审通过，指示直接开始实现）
- 当前阶段：第1点任务1.1已完成；tasks.md 原缺`域:`/`验证:`元数据，已由 Claude 按既往格式补齐后开始派单
- 当前任务：继续派单 1.2（检索/重排/候选快照/DeepSeek prompt 显式传递有序证据层）
- 📌 更正：此前 state 误记「4.2 已 commit」，实际 4.2 前端场景页与 antd/router 依赖一直是未提交 WIP，直到本圈 `12ae434` 才与 4.3/4.4 接通一并提交

> ⚠️ MCP 提醒：`codex-pro` 已通过 `claude mcp add codex-pro -e CODEX_HOME=/Users/tllrhry/.codex-pro -- codex mcp-server` 注册（local scope，`claude mcp list` 显示 ✔ Connected），但 MCP 工具在会话启动时加载，需**重启 Claude Code** 后新会话才能拿到 `mcp__codex-pro__*`。

## 已确认的当前事实

- 项目：dawenzhang（银行"五篇大文章"生成 + 国民经济分类，当前为骨架 MVP 阶段）
- 后端：FastAPI + SQLAlchemy 2.x + Alembic，Python 3.12；入口 `backend/app/main.py`，配置 `backend/app/core/config.py`
- 后端运行事实（默认值，环境变量/`.env`优先覆盖）：host `127.0.0.1`、port `8000`、API 前缀 `/api/v1`、DB `postgresql+psycopg://...`（仅接受 PostgreSQL，启用 pgvector）
- 后端命令：启动 `PYTHONPATH=backend python backend/run.py`（Makefile `backend-dev`）；测试 `PYTHONPATH=backend python -m pytest backend/tests`（Makefile `test`）；迁移 `bash backend/scripts/migrate.sh`
- 前端：React 19 + Vite 6 + TypeScript 5.7，dev 端口 5173；`npm run dev` / `npm run build`（`tsc -b && vite build`）/ `npm run test`（当前=`tsc --noEmit`，尚无运行时测试框架）
- 域：`python`、`frontend`、`misc`（本项目无 Java 域）
- 统一 runner：`scripts/run-gates.sh`（pytest + 前端 `tsc --noEmit`）

## 最近完成

- 2026-07-11：开始 `align-national-economy-classification-rules-and-result-layout`，完成**第1点 1.1**：新增 `national_economy_decision_policy.py`——四级证据层（`EvidenceLevel`：主营营收>贸易合同/产业链>贷款用途>营业执照经营范围）、`EvidenceFact`/`EvidenceLayer` 可用性判定（`is_usable`/`is_available`）、`decide_primary_business` 逐级降级取最高可用层且记录低层冲突（`EvidenceConflict`，不反转已采纳结论）、`supplement_layer_with_objection` 将异议并入既有层而非新增第五级。测试 `test_national_economy_decision_policy.py` 7 项覆盖主营营收优先/三级逐级降级(parametrize)/冲突不反转/异议补充非第五级/全不可用兜底，7 passed。**特殊情况**：该实现在本次会话开始前即以未提交状态存在（非本圈由 Codex 现场派单产出），Claude 独立复核代码与测试、确认未被其他模块引用（不与 1.2/1.3 范围冲突）、跑通测试后按常规终审流程勾选任务、更新 state。tasks.md 本身此前缺少 `域:`/`验证:` 元数据（对照 mvp change 格式补齐 10 条任务的元数据后才能走 `/dispatch`）。
- 2026-07-11：完成 national-economy-mvp **第5点 5.1–5.4**：修复首页 hero 背景剪影误占文档流导致的 155px 留白；将 Word 模板改为 13 字段三列表格并保持旧段落模板兼容；真实模型探针全部通过；真实目录同步 1 版本/3117 片段，修复 TLS 瞬时超时（连接复用+3次重试）与 Excel `A0111`→业务四位码 `0111` 规范化；最终保留案例 35，首次分类/异议重判均为 `0111 稻谷种植`、置信度 95%，历史 `[1,2]`，Excel 三工作表验证通过；README、docs 验收材料、runner、前端 build、OpenSpec strict validate 均完成。
- 2026-07-11：完成 national-economy-mvp **第4点 4.2/4.3/4.4**（前端 MVP，Codex 合并单次实现 + 1 次同 phase 打回 + Claude 独立终审，`12ae434`）：在并行会话未提交的 antd5+router UI mock 上接通真实 4.1 API——新增 `frontend/src/api.ts`（严格类型 API client：`VITE_API_BASE_URL` baseUrl、`ApiError` 统一错误解析、createCase/getCase/classifyCase/submitObjection/getHistory/template+export URL）；`App.tsx` 接通端到端流程（选 .docx→`POST cases` 建案例[422 展示 missing/duplicate/unrecognized 可操作错误并可重选重试]→"分类中"等待态禁用重复提交→`POST classifications` 长调用[502 可重试]→真实结果详情：代码/名称/百分比置信度/依据/AI 总结/13 输入字段/版本/`needs_review` 待人工复核态；异议重判追加版本、历史版本升序、Excel 导出下载；sessionStorage 会话恢复）；`vite.config.ts` 加 `/api/v1`→`127.0.0.1:8000` dev proxy。**终审抓 1 bug 打回**：后端 `objection` 是对象 `{"description":...}` 而 api.ts 误型为 string、App.tsx 直接插值会渲染 `[object Object]`——Codex 同线程修为 `ResultObjection` 类型 + `objection?.description` 渲染。Claude 独立复跑 `run-gates.sh` OVERALL PASS + `npm run build` 通过。规格缺口：后端无全局案例列表端点，历史页仅展示当前会话案例版本历史（MVP 可接受）。只 commit 前端 6 文件，未触碰后端/`.dual-agent`/AGENTS/CLAUDE/openspec。
- 2026-07-11：完成 national-economy-mvp **第4点 4.1**（Codex 一次实现 + Claude 独立终审，一次通过）：新增后端 REST API——`national_economy.py` 路由 8 端点 + `schemas/national_economy.py` + 挂载到 `settings.api_v1_prefix`（`23cb2df`）。端点：场景查询（国民经济 available；涉农 + 五篇大文章四子类 technology/green/pension/digital coming_soon，四子类带 parent_id）、模板下载（原始 .docx，路径严格 `/scenarios/national-economy/template` 对齐前端写死值，DOCX MIME+attachment）、单文件上传（`UploadFile`，`.docx` 校验；解析失败捕获 `NationalEconomyTemplateError` 返结构化 422 含 missing/duplicate/unrecognized 且不建案例）、案例查询（13 输入字段用 `FIELD_LABELS`/场景/状态/当前结论 `get_current_completed_result`）、分类（复用 `classify_case`，云端异常映射 502）、异议重判（`reclassify_case`，空/纯空白异议 422，云端异常 502）、历史（`result_versions` 按 version 升序）、Excel 导出（`export_case_workbook` 字节，XLSX MIME+attachment）。测试 `test_national_economy_api.py` 用 `TestClient`+`dependency_overrides[get_db]` 连真实 db 容器（`dawenzhang-db-1` healthy），云端分类 monkeypatch 桩含失败分支，openpyxl 读回三工作表名。Claude 独立复跑 runner OVERALL PASS，后端 pytest 累计 **66 passed**（新增 8）。只 commit 本点 5 个后端文件（routes/schemas ×2/main.py/tests），未触碰并行前端改动与 AGENTS/CLAUDE/.dual-agent。
- 2026-07-11：完成 national-economy-mvp **第3点 3.1–3.5**（Codex 逐单实现 + Claude 独立终审，5 个 phase 各新会话，均一次通过）：3.1 `NationalEconomyClassificationCase`/`NationalEconomyClassificationResult` 模型（scenario/JSONB input_payload/status/candidate_snapshot/objection/model_output/版本唯一约束/级联外键）+ 迁移 0003（`569b476`）；3.2 `national_economy_case_ingestion.py`——严格 13 稳定标签解析建案例、未填存空、缺失/重复/无法识别报错不建案例、`read_template_bytes` 返回原始 .docx，新增可配置 `NATIONAL_ECONOMY_TEMPLATE_PATH`（`3df8810`）；3.3 `national_economy_classification.py`——DeepSeek 受限分类，校验代码/名称同候选配对、0–100 置信度、依据/总结非空，`no_match` 返 needs_review 不强选，失败明确抛错不臆造（`07ec819`）；3.4 `national_economy_classification_workflow.py`——首次分类/异议重判/版本递增(max+1)、字段标签查询构造、置信度四舍五入、失败 rollback 不覆盖既有 completed、`get_current_completed_result` 取最新成功版（`5f5330b`）；3.5 `national_economy_case_export.py`——openpyxl 三工作表（案例输入/当前结论/判定历史）复用 FIELD_LABELS 与 get_current_completed_result（`dc608c4`）。每单 runner 独立复跑 OVERALL PASS，后端 pytest 累计 58 passed。均只 commit 本点后端文件，未触碰并行第4点前端改动。
- 2026-07-11：完成 national-economy-mvp **第2点 2.4**（Codex 实现 + Claude 终审）：新增 `national_economy_retrieval.py`——查询向量化（复用 `embed_texts`，校验维度）、pgvector cosine Top30 召回（`cosine_distance` + `order_by` + limit 30）、按四级 `industry_code` 聚合（取最佳距离）、硅基流动 rerank Top5–8（`/rerank`，top_n∈[5,8] 校验、index 越界与结构校验）、`EvidenceSnapshot` 证据快照（vector_score/rerank_score/命中片段）；DeepSeek 分类留待第3点。测试 9 项覆盖召回 SQL/聚合/Top5–8/快照/超时/非2xx/结构异常（云端全 mock）。runner OVERALL PASS，commit `5e10cfb`。
- 2026-07-11：完成 national-economy-mvp **第2点 2.3**（Codex 实现 + Claude 终审）：新增 `national_economy_catalog_chunks.py`——`build_industry_chunks`（definition=小类说明/include=小类补充内容/exclude=小类注释-不包括，列索引 name=2/code=3/4/5/6 与 2.2 表头一致，切片上限 1000 字符）、`embed_texts`（SiliconFlow httpx 批量，config 超时，逐向量维度校验）、`full_resync_catalog`（pgvector upsert，on_conflict 幂等键 `uq_national_economy_industry_chunk_source`）；接通 2.2 的 `full_resync` 钩子；测试断言无 .md/.jsonl 产出、分批、幂等（embedding mock）。runner OVERALL PASS，commit `d1463fd`。
- 2026-07-11：完成 national-economy-mvp **第2点 2.2**（Codex 实现 + Claude 终审）：新增 `read_catalog_source`/`synchronize_catalog`（`backend/app/services/national_economy_catalog_sync.py`）——校验精确 7 列表头（`大类名称/大类编码/小类名称/小类编码/小类说明/小类补充内容/小类注释-不包括`，已比对真实 Excel 首行一致）、SHA-256 源哈希、三元幂等键=源哈希+embedding_model+embedding_dimension，任一变化触发 `full_resync` 钩子；命令 `backend/scripts/sync_national_economy_catalog.py`（钩子留骨架给 2.3）；新增 `openpyxl` 依赖；测试覆盖表头校验/幂等跳过/三元变更触发重同步（embedding mock）。runner OVERALL PASS，commit `4c30630`。
- 2026-07-11：完成 national-economy-mvp **第2点 2.1**（Codex 实现 + Claude 终审）：新增 `NationalEconomyCatalogVersion`/`NationalEconomyIndustryChunk` 模型（`backend/app/models/national_economy.py`）与 Alembic 0002 迁移（`VECTOR(settings.embedding_dimension)`，不写死维度），字段含 code/name/source_row/text/chunk_type/source_hash/version + pgvector；版本幂等键=源哈希+embedding_model+embedding_dimension（对齐 2.2）；注册进 `app.models`/`alembic/env.py`；新增建表与 pgvector 列断言测试。runner 独立复跑 OVERALL PASS，migrate.sh PASS，commit `e13b303`。
- 2026-07-11：完成 national-economy-mvp **第1点**（1.1–1.3）：SQLite→PostgreSQL+pgvector（config 强制 postgresql、连接池、psycopg v3）、docker-compose 新增 pgvector db 服务（2C4G 调优+healthcheck+只读挂载 Excel）、0001 迁移启用 vector 扩展、云端 API 环境变量（硅基流动/DeepSeek）与分层超时（30s/120s/nginx+uvicorn 190s）、健康检查区分 DB(含pgvector)与模型配置、`backend/scripts/probe_models.py` 实测三 API（embed dim=4096/rerank 结构/DeepSeek JSON 全 PASS）、更新 config/health 测试。runner OVERALL PASS，commit `3b31f28`。补齐 2.1–2.4 的 域/验证 元数据，校准 `dispatch/python.md` 为 PostgreSQL+pgvector。
- 2026-07-11：从 ai_tag_fix 移植双 Agent + loop 机制到本项目——`.dual-agent/`（core/loop/index/state/contracts/env-diff/failures/loop-log + dispatch 模板）、`.claude/skills/dispatch/`、`scripts/run-gates.sh`、CLAUDE.md/AGENTS.md 双 Agent 入口段、`CLAUDE.local.md`。只搬机制，不含 ai_tag_fix 业务契约；`failures.md` 仅带 6 条跨项目通用工作流教训作种子。

## 未决与下一步

- **下一步**：用户验收首页与表格化 Word；确认后可归档 `implement-national-economy-classification-mvp`，本轮不自动归档。
- 前端真实联调需 db 容器 + 后端起 + 已同步目录 + 真实云端密钥；dev 走 vite proxy（已加）或 `VITE_API_BASE_URL`。人工端到端核对项见 4.3/4.4 验证元数据。
- `dispatch/python.md` 已校准为 PostgreSQL+pgvector；`frontend.md` 已校准（antd5/router、`VITE_API_BASE_URL`、dev proxy 到 8000）
- `contracts.md`、`env-diff.md` 仍为空，待真实契约/差异出现再填（如：embedding 维度 4096 与 `EMBEDDING_DIMENSION` 一致性、云端 API 出网前置条件）
- tasks.md 2.4.1/2.4.2 的真实 API key 已脱敏为指向 `.env`；真实运行密钥仅存 `.env`（gitignore）。含密钥的本地提交 97d9fb1 已弃（reset 到 bc1a41b 重组为无密钥的 3b31f28）；密钥从未推送上云
- openspec/ 已加入 .gitignore 并取消跟踪（commit 0ce894c），远程 HEAD 树已无 openspec；本地文件保留供双 Agent 流程；旧历史提交仍含无密钥 openspec（未重写历史）
