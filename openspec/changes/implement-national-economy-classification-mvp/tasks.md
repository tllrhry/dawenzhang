## 1. PostgreSQL、pgvector 与云端模型准备

- [ ] 1.1 将演示 SQLite 配置替换为 PostgreSQL 开发/部署配置，docker-compose 使用 `pgvector/pgvector:pg16` 镜像，在数据库初始化中启用 pgvector 扩展，并为 2C4G 环境设置适度连接与内存参数
- [ ] 1.2 更新后端依赖、Docker 编排、健康检查和环境变量示例，配置 PostgreSQL、原始资料挂载路径、硅基流动 embedding/rerank 与 DeepSeek 官方 API，并逐层配置超时（embedding/rerank 30s、DeepSeek 120s、nginx `proxy_read_timeout`/uvicorn ≥180s）
- [ ] 1.3 编写硅基流动 embedding/rerank 与 DeepSeek API 探针，使用真实配置验证模型标识、响应结构、embedding 维度、批量限制和超时

## 2. 行业知识库同步与检索

- [ ] 2.1 新增目录版本和行业检索片段的 SQLAlchemy 模型及 Alembic 迁移，包含代码、名称、源行、文本、片段类型、源哈希、版本和 pgvector 列
- [ ] 2.2 实现从 `NATIONAL_ECONOMY_CATALOG_PATH` 读取原始 Excel 的幂等同步命令，校验表头并以“源哈希 + embedding 模型标识 + 向量维度”作为版本幂等键，任一变化触发全量重新同步
- [ ] 2.3 实现行业定义、包括和不包括内容的受限长度切片、批量 embedding 和 PostgreSQL upsert；不得输出 Markdown/JSONL 等大体量索引文件
- [ ] 2.4 实现企业查询向量化、pgvector Top 30 召回、按行业代码聚合、硅基流动 rerank Top 5–8 和证据快照服务

## 3. 后端案例与分类领域

- [ ] 3.1 新增分类案例、分类结果历史的数据模型及 Alembic 迁移，保存场景、JSONB 输入、状态、候选快照、异议和模型输出
- [ ] 3.2 实现模板下载和单企业 `.docx` 解析服务，按 13 个稳定标签创建案例并报告缺失、重复或无法识别的标签
- [ ] 3.3 实现 DeepSeek 受限分类服务，验证唯一代码/名称配对、0–100 置信度、匹配依据和 AI 总结；支持模型显式返回“候选均不匹配”（`no_match`）时保存待人工复核结果版本而非强选
- [ ] 3.4 实现首次分类、异议重判和版本追加服务，确保失败不会覆盖最近成功结论
- [ ] 3.5 实现案例输入、当前结论和完整历史的 Excel 工作簿导出服务

## 4. 后端 API 与前端 MVP 流程

- [ ] 4.1 增加可用/未开放业务场景查询、国民经济模板下载、单文件上传、案例查询、分类、异议、历史和 Excel 导出 API
- [ ] 4.2 前端引入 Ant Design 5（默认主题、中文 locale）与 `react-router-dom`，将构建工具移入 `devDependencies`，并将健康检查首页替换为数据驱动的业务场景选择页，展示国民经济可用入口及涉农、五篇大文章（含四子类）的暂未开放状态
- [ ] 4.3 实现国民经济模板下载、单文件上传、解析/分类状态（含“分类中”等待态与禁用重复提交）、失败重试和结果详情界面
- [ ] 4.4 实现结果的代码、名称、百分比置信度、匹配依据、AI 总结、版本历史、异议重判、待人工复核状态展示和 Excel 导出界面

## 5. 验证与交付

- [ ] 5.1 为目录切片、同步幂等性、pgvector 召回/聚合、rerank、模型输出校验和异议版本追加编写单元测试，并以 mock 覆盖云端 API 失败分支
- [ ] 5.2 为上传、分类、异议、历史和导出 API 编写 PostgreSQL 集成测试，确认导出的 Excel 含“案例输入”“当前结论”“判定历史”工作表
- [ ] 5.3 使用真实 API 探针和一份填写完成的 Word 验证完整闭环：同步目录、上传、召回、rerank、分类、异议重判、查看历史并导出 Excel
- [ ] 5.4 更新 README 的 PostgreSQL/pgvector 启动、云端 API 配置、目录同步和 MVP 范围说明，并运行前后端测试
