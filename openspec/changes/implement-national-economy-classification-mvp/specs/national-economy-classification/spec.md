## ADDED Requirements

### Requirement: pgvector-backed national-economy knowledge base
系统 SHALL 使用 PostgreSQL 的 pgvector 扩展保存由 `国民经济行业分类V1-0814.xlsx` 同步出的行业检索片段及 embedding。每个片段 SHALL 保存所属四级行业代码、行业名称、源行、片段类型、原文、源文件哈希和目录版本；目录版本的幂等键 SHALL 由源文件哈希、embedding 模型标识和向量维度共同构成，任一变化 SHALL 触发全量重新同步；原始 Excel SHALL 是唯一业务事实来源。

#### Scenario: Initial catalog synchronization
- **WHEN** 管理员对尚未同步的原始 Excel 执行目录同步命令
- **THEN** 系统将每个四级行业的定义、包括/不包括内容切分为可检索片段，调用 embedding API 并写入 PostgreSQL

#### Scenario: Synchronize an unchanged catalog
- **WHEN** 管理员在源文件哈希、embedding 模型标识和向量维度均未变化时再次执行目录同步命令
- **THEN** 系统不重复创建行业片段或 embedding，并报告当前目录版本已存在

#### Scenario: Re-synchronize after switching the embedding model
- **WHEN** 管理员在源 Excel 未变化但 embedding 模型标识或向量维度已变化时执行目录同步命令
- **THEN** 系统创建新的目录版本并对全部片段重新生成 embedding，不复用旧模型产生的向量

### Requirement: Cloud-assisted two-stage candidate retrieval
系统 SHALL 使用硅基流动 Embedding API 为企业分类查询生成向量，以 pgvector 召回最多 30 个行业片段，按四级行业代码聚合候选，并使用硅基流动 Rerank API 将候选重排为最多 8 个行业。系统 MUST NOT 将全量 Excel、全量行业目录或大体量预处理文本传给 rerank 或 DeepSeek。

#### Scenario: Retrieve candidates for a submitted enterprise
- **WHEN** 系统对待分类案例执行国民经济检索
- **THEN** 系统使用企业经营信息召回、聚合并重排候选行业，保留每个候选的可追溯命中证据

### Requirement: Constrained single-result classification
系统 SHALL 根据重排后的候选行业调用 DeepSeek 官方 API，并要求模型选择唯一的 GB/T 4754-2017 四级行业结论，或显式声明候选中不存在合适行业（`no_match`）。选中候选时系统 SHALL 返回且持久化四级行业代码、行业名称、0 至 100 的数字置信度、匹配依据和 AI 总结；系统 MUST NOT 在模型声明候选均不匹配时强制写入某个候选作为结论。

#### Scenario: Successful initial classification
- **WHEN** 一个待分类案例已得到重排候选且 DeepSeek 返回有效结果
- **THEN** 系统保存一个与候选目录代码和名称完全匹配的首版结论，并将案例标记为已完成

#### Scenario: No suitable candidate
- **WHEN** DeepSeek 显式返回候选中不存在合适行业及其理由
- **THEN** 系统保存一个“候选均不匹配”的结果版本（含候选快照和模型理由），将案例标记为待人工复核，并提示用户可通过异议补充经营信息触发重新检索与重判

#### Scenario: Invalid model output
- **WHEN** 模型返回的代码/名称不属于重排候选、置信度不在 0 至 100 范围内或缺少必填结论字段
- **THEN** 系统不保存该结论，将案例标记为分类失败并返回可重试的错误信息

### Requirement: Evidence limited to available sources
系统 SHALL 在匹配依据中说明使用的企业输入与目录中命中的定义、包括或不包括片段。系统 MUST NOT 声称命中企业清单、涉农规则、五篇大文章标签或未提供的硬规则。

#### Scenario: Generate a result without a company list
- **WHEN** 系统完成本期国民经济分类
- **THEN** 匹配依据只引用案例输入和已同步行业目录中的可追溯内容
