## Context

项目已有 React + Vite、FastAPI 和 SQLite 演示骨架，但没有业务页面、领域数据或判定服务。国民经济 Excel 有 1,382 条四级行业记录，包含行业代码、名称、定义、包括和不包括说明；单企业 Word 模板有 13 个固定输入字段。

本期只实现国民经济行业分类闭环。涉农和五篇大文章（科技、绿色、养老、数字金融）只保留前端未开放入口，五级标签不属于本期输出。用户已确认：硅基流动云端 API 负责 embedding 和 rerank，DeepSeek 官方 API 负责最终结构化分类；2C4G 环境不引入 Milvus。

## Goals / Non-Goals

**Goals:**

- 支持单企业 Word 模板的下载、上传、解析、分类、异议重判和 Excel 导出。
- 使用 PostgreSQL + pgvector 将行业目录变成可追溯的向量知识库，只把少量重排后的候选发送给 DeepSeek。
- 保存原始结构化输入与每一次判定历史，保证代码、名称与来源目录可校验。
- 将目录同步限制为数据库写入，不在 Git 或发布目录生成大体量检索文本资产。

**Non-Goals:**

- 不实现涉农结论、五篇大文章标签、企业名单匹配或额外硬规则数据源。
- 不使用 MySQL、SQLite 向量扩展、Milvus、独立对象存储或消息队列。
- 不提供批量上传、多候选输出、人工维护目录 UI、模型训练或生产级安全能力。

## Decisions

### 1. PostgreSQL + pgvector 作为唯一运行时数据库

应用从 SQLite 演示数据库迁移到 PostgreSQL，并在初始化迁移中执行 `CREATE EXTENSION IF NOT EXISTS vector`。业务表保存案例、结论版本和异议；目录表保存目录版本、行业片段、行业代码/名称、源行、原始片段文本和 embedding。这样避免将向量塞入 SQLite/MySQL，同时不需要为数千片段维护 Milvus。

初版按硅基流动 embedding 实际返回维度创建 `vector(n)` 列。行业片段预计只有数千条，pgvector 先采用余弦距离精确检索；达到更大规模后再评估 HNSW。替代方案是 Milvus 或 pgvector 以外的独立向量库：前者在 2C4G 环境中运维和内存成本不匹配，后者会增加额外服务与数据同步。

### 2. 目录通过显式同步命令从原始 Excel 写入数据库

原始 Excel 仍是唯一事实来源，运行环境通过 `NATIONAL_ECONOMY_CATALOG_PATH` 提供文件路径。受控的同步命令以“源文件 SHA-256 + embedding 模型标识 + 向量维度”作为目录版本的幂等键：三者中任一变化都触发重新切片和重新 embedding，避免换模型后库内向量与查询向量来自不同模型而检索静默失效。同步命令读取表头和行数据，将每个四级行业切为“定义”和若干“包括/不包括”短片段，每个片段都绑定行业代码、名称和源行。

同步命令批量调用硅基流动 Embedding API 并幂等 upsert PostgreSQL；源未变时不重复生成 embedding。它不生成 Markdown、JSONL 或其他可提交的大文本文件。替代方案是在服务启动时全量同步：启动时间和云端 API 调用不可控，因此不采用。

### 3. 使用向量召回、行业聚合和云端重排的两阶段检索

分类请求从主营业务、核心产品/服务、营业执照经营范围和贷款用途构造带字段标签的查询；其余输入作为补充上下文。服务调用硅基流动 Embedding API 生成查询向量，以 pgvector 余弦距离召回 Top 30 行业片段，按四级行业代码聚合为候选行业，并将每个行业的最佳命中片段提交给硅基流动 Rerank API，取 Top 5–8 个行业。

每个候选向 DeepSeek 仅携带代码、名称、定义和被检索/重排命中的精简证据片段，严格控制上下文长度。向量召回负责语义覆盖，rerank 解决相近行业的排序；不将全量 Excel 或完整长说明传给模型。

### 4. DeepSeek 在候选中产生唯一有效结论，或显式声明候选均不匹配

DeepSeek 官方接口接收企业输入、异议（如有）和 Top 5–8 候选，返回 `industry_code`、`industry_name`、`confidence_percent`、`matching_basis`、`summary`。服务端要求代码和名称完全匹配候选目录，置信度为 0–100 数字，且依据和总结非空；不符合时记录失败而不写入结论。

模型另可返回 `no_match: true` 及说明理由，表示候选中不存在合适行业。此时服务保存一个“候选均不匹配”结果版本（含候选快照与模型理由），将案例标记为待人工复核，不强迫模型在错误候选中硬选。用户可通过异议通道补充经营信息触发重新检索与重判——这是向量召回漏掉正确行业时的兜底出口。

硅基流动与 DeepSeek 使用独立的 URL、密钥、模型和超时环境变量。替代方案是让 DeepSeek 直接从全部目录自由生成代码，因上下文成本、幻觉和可审计性问题不采用。

### 5. Word 输入和结论采用关系数据 + JSONB 版本历史

模板下载返回原始 `.docx`；上传服务用 `python-docx` 按 13 个固定标签解析并创建一个案例。案例输入以 PostgreSQL JSONB 保存，结论版本保存候选快照、检索证据、异议、模型配置与最终结构化输出。异议创建新版本，不覆盖旧版本，当前结论取最新成功版本。

### 6. 单企业 MVP 采用同步调用和后端 Excel 导出

上传后前端触发分类；分类请求内依次调用 embedding、pgvector、rerank、DeepSeek。整条链路必须显式配置超时：embedding/rerank 单次调用超时 30 秒，DeepSeek 调用超时 120 秒，nginx `proxy_read_timeout` 与 uvicorn 保持不低于 180 秒，分类接口整体超时预算 180 秒。前端在等待期间展示明确的“分类中”状态并禁用重复提交，超时或失败时给出可重试提示。后端生成含“案例输入”“当前结论”“判定历史”三工作表的 Excel。单企业链路的同步延迟可接受；未来批量化时再将同一命令模型移入队列。

### 7. 前端采用 Ant Design 5 + React Router

前端在现有 React 19 + Vite + TypeScript 骨架上引入 Ant Design 5 作为唯一 UI 组件库（默认主题、中文 locale），场景选择、上传、结果、历史等页面使用 `react-router-dom` 组织路由。不引入额外状态管理库，MVP 用 React 内置状态与 fetch 封装即可。`vite`、`typescript`、`@vitejs/plugin-react` 等构建工具归入 `devDependencies`。

## Risks / Trade-offs

- [硅基流动模型/向量维度与配置不匹配] → 实施前通过真实 API 探针验证 embedding、rerank、维度、批量和超时，再创建迁移与索引。
- [向量召回遗漏正确行业] → 召回 30 个片段、按行业聚合后再 rerank，记录候选和证据快照；模型可显式返回“候选均不匹配”转人工复核，并将用户异议纳入重判。
- [更换 embedding 模型导致库内向量失效] → 目录版本幂等键包含 embedding 模型标识与维度，换模型自动触发全量重新同步。
- [DeepSeek 不可用或返回无效 JSON] → 明确失败状态和可重试操作，不覆盖最近成功结论。
- [同步分类链路超时被反代截断] → nginx/uvicorn/HTTP 客户端逐层配置超时（DeepSeek 120s、整体 180s），前端展示分类中状态并支持失败重试。
- [源 Excel 更新] → 以 SHA-256 控制幂等同步，保留目录版本和源行，便于重建与追溯。
- [PostgreSQL 服务不可用] → 健康检查区分数据库、硅基流动和 DeepSeek 状态；MVP 不尝试用 SQLite 降级向量检索。
- [2C4G 服务器构建前端 OOM] → 前端镜像在本地或 CI 构建后推送部署，不在目标服务器上执行 `vite build`；如必须在服务器构建，先配置至少 2G swap。
- [部署环境出网受限] → 服务器必须能访问硅基流动与 DeepSeek 公网 API，属部署前置条件，写入 README；出网配置由使用方在实施时提供。

## Migration Plan

1. 在 2C4G 环境用 `pgvector/pgvector:pg16` 镜像部署单个 PostgreSQL 实例（扩展已内置），配置受限连接数与适度内存参数（如 `shared_buffers=256MB`、`max_connections=20`）。
2. 将应用 `DATABASE_URL` 改为 PostgreSQL，新增 Alembic 迁移创建业务表、目录表和 `vector(n)` 列；未存在需迁移的真实 SQLite 业务数据时，不执行数据搬迁。
3. 确认服务器可出网访问硅基流动与 DeepSeek API，配置原始 Excel/Word 的挂载路径、硅基流动和 DeepSeek 环境变量及各层超时，先运行 API 探针。
4. 前端镜像在本地或 CI 构建后推送到服务器；执行目录同步命令，确认目录记录、片段、源哈希及 embedding 数量后启动前后端。
5. 用一份填写完成的 Word 完整验证上传、召回、rerank、分类、异议、历史和 Excel 导出。

回滚时停止新应用并回退本 change 的迁移；目录向量与业务数据都位于独立 PostgreSQL 数据库中，不影响其他项目服务。

## Open Questions

无。硅基流动与 DeepSeek 的最终模型标识、端点和密钥通过环境变量提供，并在实施任务的 API 探针中验证。
