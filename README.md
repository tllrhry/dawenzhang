# 大文章智能分类 MVP

本项目提供 React + TypeScript + Vite 前端和 FastAPI 后端。当前 MVP 已实现“国民经济行业分类”完整闭环：下载并填写单企业 Word 模板、上传解析 13 个经营字段、通过 PostgreSQL + pgvector 召回行业候选、使用硅基流动 rerank 重排、由 DeepSeek 生成唯一四级行业结论，并支持异议重判、版本历史和 Excel 导出。

涉农分类和五篇大文章分类目前仅展示“暂未开放”，不进入上传或判定流程。

## 前置条件

- Python 3.12+
- Node.js 22+ 和 npm
- Docker 与 Docker Compose
- 可访问硅基流动和 DeepSeek 公网 API

不需要 MySQL、Redis、RabbitMQ、Milvus、MinIO 或本地模型服务。

## 本地启动

首次运行先准备配置和依赖：

```bash
cp .env.example .env
# 在 .env 中填写 SILICONFLOW_API_KEY 和 DEEPSEEK_API_KEY
python -m pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..
```

然后使用统一入口启动 PostgreSQL、执行数据库迁移并启动前后端：

```bash
./start.sh
```

- 前端：<http://127.0.0.1:5173>
- 后端健康检查：<http://127.0.0.1:8000/api/v1/health>
- API 文档：<http://127.0.0.1:8000/docs>

`start.sh` 在本地只用 Docker Compose 托管 PostgreSQL；FastAPI 和 Vite 在宿主机运行，便于热更新。重复执行脚本会复用已经监听的前后端服务。

## 云端模型配置

`.env.example` 包含完整配置项，关键变量如下：

```dotenv
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_API_KEY=
SILICONFLOW_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
SILICONFLOW_RERANK_MODEL=Qwen/Qwen3-Reranker-8B
EMBEDDING_DIMENSION=4096

DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
```

密钥只保存在本地 `.env`，不得提交到 Git。可在同步目录前运行真实探针验证模型、响应结构和向量维度：

```bash
PYTHONPATH=backend python backend/scripts/probe_models.py
```

## 同步国民经济行业目录

原始 Excel 是行业目录唯一事实来源，通过 `NATIONAL_ECONOMY_CATALOG_PATH` 配置。首次运行分类前必须同步目录：

```bash
PYTHONPATH=backend python backend/scripts/sync_national_economy_catalog.py
```

同步命令会读取 Excel、构建受限长度片段、批量调用硅基流动 embedding，并将片段和 4096 维向量写入 PostgreSQL + pgvector。目录版本以“源文件哈希 + embedding 模型 + 向量维度”为幂等键；配置未变化时重复执行会跳过重新生成。

## Word 填写与分类流程

下载的 Word 模板采用“字段名称 / 填写内容 / 填写提示”三列表格。每个文件只填写一家企业，保留第一列 13 个固定字段名称，在第二列填写内容，第三列仅用于说明。旧版 `字段：内容` 段落模板仍可继续上传。

用户流程：

1. 在首页进入“国民经济行业分类”。
2. 下载 Word 模板并填写企业经营信息。
3. 上传 `.docx`，系统解析并创建待分类案例。
4. 发起分类，等待 embedding、pgvector 召回、rerank 和 DeepSeek 判定。
5. 查看代码、名称、置信度、依据和 AI 总结。
6. 如有异议，补充说明并触发新版本重判。
7. 查看历史并导出含“案例输入”“当前结论”“判定历史”的 Excel。

真实闭环场景、填写模板、导出文件和验收记录位于 `docs/national-economy-e2e/`。

## Docker Compose 部署

部署环境可以使用 Compose 构建 PostgreSQL + pgvector、FastAPI 和 Nginx 前端：

```bash
cp .env.docker.example .env
# 填写云端 API 密钥，并按需设置 HTTP_PORT
docker compose up --build -d
```

数据库数据默认持久化到 `./data/pgdata`，上传与导出文件位于 `./data`。原始目录 Excel 通过只读挂载提供，不会打包进镜像。生产环境应在前端容器之前配置 HTTPS，并确保反向代理读取超时不低于 180 秒。

## MVP 范围与约束

- 运行时数据库仅支持 PostgreSQL，并依赖 pgvector 扩展。
- 当前只支持单企业 `.docx`，不支持批量上传。
- 当前只输出一个 GB/T 4754 四位小类代码和名称，或返回“候选均不匹配”转人工复核。
- embedding/rerank 使用硅基流动，最终分类使用 DeepSeek；云端不可用时明确失败，不伪造结论。
- 不实现涉农、五篇大文章标签、企业名单硬匹配、消息队列或本地模型服务。

## 验证

统一运行前后端检查：

```bash
bash scripts/run-gates.sh
```

也可以分别执行：

```bash
PYTHONPATH=backend python -m pytest backend/tests
cd frontend && npm run test && npm run build
```
