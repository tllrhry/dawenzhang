## Context

项目当前没有应用代码，已有资料包括需求计划、Word 模板和行业/政策 Excel。宿主机已经运行 `ai_tag_fix` 项目的 MySQL 8、Redis 7、RabbitMQ、Milvus、MinIO 和 etcd。现有 MySQL 的业务库为 `ai_tag_fix`，现有 Java 项目明确使用 Redis `db0`；本项目需要共享服务进程，但必须隔离数据。

## Goals / Non-Goals

**Goals:**

- 建立 React + TypeScript + Vite 与 FastAPI 的最小可运行骨架。
- 通过配置和健康检查明确 MySQL/Redis 的目标实例与隔离边界。
- 创建独立 `dawenzhang` MySQL 数据库、应用用户和迁移入口。
- 固定使用 Redis `db1`，并以 `dawenzhang:` 作为 key 命名空间。
- 为后续 Word 解析、规则引擎、AI 和导出模块提供清晰的扩展位置。

**Non-Goals:**

- 不实现业务判定规则、Word 字段解析、AI 调用、异议重判或 Excel 导出。
- 不新增或管理 MySQL、Redis 容器。
- 不在本阶段启用 Milvus/RAG、MinIO 文件服务或 RabbitMQ 任务编排。
- 不建设生产级认证、权限、审计和多租户能力。

## Decisions

### 1. 使用前后端分离的单仓库结构

采用 `frontend/` 和 `backend/` 两个应用目录。前端使用 React、TypeScript、Vite；后端使用 FastAPI。这样与计划文档一致，也便于后续页面和判定 API 并行开发。

替代方案是 Streamlit 或把前端嵌入 FastAPI；它们启动更快，但不适合计划中的多页面上传、确认、结果详情和异议流程，因此不采用。

### 2. MySQL 共享实例、独立数据库和应用用户

项目使用现有 MySQL 实例的 3306 端口，但创建 `dawenzhang` 数据库和专用应用用户。后端使用 SQLAlchemy 连接，数据库结构使用 Alembic 迁移管理；管理员初始化脚本只执行 `CREATE DATABASE/USER IF NOT EXISTS` 和授权，不包含删除或重置操作。

数据库连接配置必须包含数据库名，并在启动检查中拒绝 `ai_tag_fix`，避免误连现有项目。真实密码仅通过环境变量提供。

替代方案是继续使用 SQLite，或在同一 `ai_tag_fix` 库中建表。SQLite 不利于后续并发和审计；共用业务库则会造成表、迁移和权限耦合，因此不采用。

### 3. Redis 使用 db1 和 key 前缀双重隔离

项目固定默认 `REDIS_DB=1`，同时由 Redis 适配层统一增加 `dawenzhang:` 前缀。现有项目的配置和运行状态表明其使用 `db0`，因此 db1 是本项目的隔离边界；双重隔离可以降低误读同实例其他 key 的风险。

缓存清理命令只允许删除本项目前缀 key，或在明确指定时清理 db1，不允许执行全局 `FLUSHALL`。

### 4. 支持宿主机和已有 Docker 网络两种开发方式

默认支持宿主机运行后端，连接 `127.0.0.1:3306` 和 `127.0.0.1:6379`。若后端容器化，则将应用容器加入已有的 `ai_tag_fix_default` 外部网络，使用 `ai_tag_fix_mysql` 和 `ai_tag_fix_redis` 作为服务地址；本项目编排文件不声明 MySQL/Redis 服务。

### 5. 基础设施按需启用

RabbitMQ 仅在后续确实需要长任务队列时接入；Milvus 仅在出现需要向量检索的语义匹配方案时接入；MVP 基础框架先使用本地文件存储和可配置 AI HTTP 接口。这样不会把现有平台的全部组件强行耦合进第一阶段。

## Risks / Trade-offs

- [共享 MySQL 实例误操作] → 使用独立数据库用户、启动时拒绝 `ai_tag_fix`、初始化脚本禁止 destructive SQL，并在迁移前打印目标数据库。
- [Redis db1 被其他项目占用] → 启动时检查连接的 database index 和项目 key 前缀；正式实施前确认 db1 无现有业务归属。
- [外部 Docker 网络不存在] → 宿主机模式作为默认开发模式；Docker 启动前检查网络并给出明确错误，不自动创建同名替代网络。
- [数据库初始化权限不足] → 将管理员初始化和应用运行凭据分离，提供一次性管理员脚本和普通应用连接配置。
- [后续 AI/解析任务耗时] → 先定义服务接口和任务状态模型，后续可接 RabbitMQ，不在基础框架阶段提前引入队列复杂度。

## Migration Plan

1. 准备未提交的本地环境配置，确认 MySQL 管理连接指向现有实例。
2. 执行幂等初始化脚本，创建 `dawenzhang` 数据库和应用用户。
3. 使用应用用户执行 Alembic 初始迁移，并通过健康检查确认目标数据库为 `dawenzhang`。
4. 配置 Redis database index 为 `1`，验证读写 key 均带 `dawenzhang:` 前缀。
5. 启动前后端骨架并执行基础检查。

回滚时只回退本项目新增的迁移和应用用户；不得删除共享 MySQL 实例、现有 `ai_tag_fix` 数据库或 Redis `db0`。如需清理本项目数据，必须使用显式、人工确认的项目数据库清理命令。

## Open Questions

- 应用用户的实际名称和由谁提供生产/开发密码，需要在实施前确认；默认建议使用 `dawenzhang_app`。
- 后端首选宿主机运行还是容器运行，需要在脚手架实现时确定默认命令；两种连接模式都会保留。
- Word 解析和 AI 判定是否需要接入 RabbitMQ，待第一版接口耗时和并发需求明确后决定。
