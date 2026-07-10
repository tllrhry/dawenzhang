## Why

当前项目只有需求文档、Word 模板和 Excel 数据，尚无可运行的前后端骨架。MVP 需要一个可持续扩展的 React + FastAPI 基础，同时复用本机已有的 MySQL 和 Redis，避免为本项目重复启动基础设施容器，并确保数据与现有 `ai_tag_fix` 项目隔离。

## What Changes

- 初始化前后端分离的项目骨架：React + TypeScript + Vite 前端，Python + FastAPI 后端。
- 建立统一的环境变量配置、开发启动方式和健康检查接口。
- 在现有 MySQL 8 实例中创建独立的 `dawenzhang` 数据库及应用用户，禁止连接或修改 `ai_tag_fix` 数据库。
- 使用现有 Redis 7 实例的独立 logical DB `1`，并为本项目增加 `dawenzhang:` key 前缀隔离。
- 提供 MySQL 初始化/迁移入口和 Redis 连通性检查，不新增 MySQL 或 Redis 容器。
- 明确 RabbitMQ、Milvus、MinIO 暂不作为本基础框架的强制依赖。

## Capabilities

### New Capabilities

- `project-scaffold`: 提供前后端目录结构、开发配置、健康检查和基础启动入口。
- `shared-infrastructure`: 提供复用现有 MySQL/Redis 实例时的数据隔离、初始化和连接约束。

### Modified Capabilities

无。

## Impact

- 新增 `frontend/`、`backend/`、配置示例、数据库初始化/迁移目录和基础文档。
- 依赖 React/Vite、FastAPI、SQLAlchemy/Alembic、MySQL 驱动和 Redis 客户端。
- 需要对现有 MySQL 实例执行一次幂等的数据库/用户初始化；不修改 `ai_tag_fix` 库和现有 Redis `db0`。
- 后续 Word 解析、判定规则、AI 调用、结果导出将在此骨架上继续实现，本 change 不包含这些业务功能。
