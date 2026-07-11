# Python 域差异

FastAPI + SQLAlchemy 2.x + Alembic，Python 3.12。配置只经 `app/core/config.py` 的 pydantic-settings（环境变量/`.env` 优先，字段带 `validation_alias`），不散写 `os.getenv`。

DB 仅 PostgreSQL + pgvector（`validate_database_url` 强制 `postgresql*`，非 postgres 拒绝）；本机通过 `docker compose up -d db`（`pgvector/pgvector:pg16`，端口 5432）提供，扩展由 `0001` 迁移 `CREATE EXTENSION IF NOT EXISTS vector` 启用。向量列用 `pgvector.sqlalchemy.Vector(settings.embedding_dimension)`（当前 4096），不要写死维度字面量。

云端模型：硅基流动 embedding/rerank 与 DeepSeek 各自 base_url/key/model/timeout 均在 `config.py`（`siliconflow_*`、`deepseek_*`、`embedding_dimension`、`*_timeout_seconds`）。HTTP 客户端用 `httpx` 并显式传超时；单元测试对云端调用一律 mock（含失败分支），不打真实 API。真实 API 探针见 `backend/scripts/probe_models.py`，属手动验证，不进 pytest gate。

测试用 pytest：`PYTHONPATH=backend python -m pytest backend/tests`（本地需先起 db 容器）。改数据模型须配套 Alembic 迁移（`backend/scripts/migrate.sh`），不手改库。路由挂在 `settings.api_v1_prefix`（默认 `/api/v1`）下，别写死前缀字面量。
