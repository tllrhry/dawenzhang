## Why

现有项目只有基础前后端骨架，客户经理无法通过统一流程提交企业资料并取得可复核的 GB/T 4754-2017 四级行业结论。行业目录的语义说明较长且与企业经营描述存在措辞差异，需要先以向量检索和重排缩小候选，再让模型作唯一分类，而不能将全量 Excel 交给模型。

## What Changes

- 提供业务场景选择页：国民经济行业分类可进入完整流程；涉农、五篇大文章及其子类显示“暂未开放”。
- 支持下载既有的国民经济 Word 模板、上传已填写的单企业 `.docx`，解析 13 个固定字段并持久化为分类案例。
- 用 PostgreSQL + pgvector 替换当前演示 SQLite 存储：同一数据库保存业务案例、结果历史及行业检索片段向量。
- 提供幂等行业目录同步命令：从配置路径读取原始 Excel，将行业说明切分为带行业代码、源行的检索片段，通过硅基流动 Embedding API 写入 pgvector；目录版本以“源哈希 + embedding 模型 + 维度”为幂等键；不生成或提交大体量 Markdown/JSON 索引文件。
- 以 pgvector 召回候选、硅基流动 Rerank 重排，并调用 DeepSeek 官方 API 在少量候选中输出唯一四级行业代码、名称、百分比置信度、匹配依据和 AI 总结；模型可显式声明候选均不匹配，案例转待人工复核。
- 提供结果详情、针对当前结论的异议说明与重判，保留原判定、异议和每次重判历史，并支持导出 Excel。
- 前端基于 React + Ant Design 5 + react-router-dom 实现场景选择、上传、结果与历史页面，分类等待期展示明确的处理中状态；全链路（nginx、uvicorn、云端 API 客户端）显式配置超时。

## Capabilities

### New Capabilities

- `business-scenario-entry`: 选择业务场景、下载国民经济模板，并清楚标识暂未开放的后续场景。
- `national-economy-case-ingestion`: 接收并解析单企业 Word 模板，校验和保存统一的案例输入。
- `national-economy-classification`: 将 GB/T 4754-2017 目录同步为 pgvector 检索知识库，经云端 embedding/rerank 召回候选，并由 DeepSeek 形成唯一、可追溯的四级行业结论。
- `classification-review-and-export`: 展示结论与判定历史，处理异议重判，并导出 Excel 使用结果。

### Modified Capabilities

无。

## Impact

- 当前 SQLite 演示数据库将迁移为 PostgreSQL，并启用 `pgvector` 扩展；不使用 MySQL、Milvus 或独立向量数据库服务。
- 后端新增案例、结果历史、目录版本和行业检索片段的数据模型，及目录同步、上传、分类、异议、查询、导出 API/命令。
- 新增 Word 解析、PostgreSQL 驱动、pgvector、硅基流动 embedding/rerank、DeepSeek 官方 HTTP 客户端、Excel 导出依赖和测试夹具。
- 原始 Excel 和 Word 不进入 Git；运行环境通过配置路径挂载它们，目录同步产生的数据只写 PostgreSQL。
