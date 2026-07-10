# 大文章智能分类 MVP 基础骨架

本项目提供 React + TypeScript + Vite 前端和 Python + FastAPI 后端。当前 change 只包含可运行骨架、基础设施隔离和健康检查，不包含 Word 解析、判定规则、AI 调用或 Excel 导出业务。

## 前置条件

- Python 3.12+
- Node.js 22+ 和 npm
- 已运行的 MySQL 8（默认 `127.0.0.1:3306`）
- 已运行的 Redis 7（默认 `127.0.0.1:6379`）

项目只复用现有 MySQL/Redis，不会通过 Compose 创建新的基础设施容器。MySQL 应用库固定为 `dawenzhang`，Redis 固定为 logical DB `1`；现有 `ai_tag_fix` 库和 Redis db0 不会被应用访问或清理。

## 宿主机开发

```bash
cp .env.example .env
# 编辑 .env，填写 dawenzhang_app 的密码
python -m pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..

# 首次执行：管理员凭据只用于创建项目库和应用用户
MYSQL_ADMIN_PASSWORD='管理员密码' MYSQL_APP_PASSWORD='应用密码' \
  bash backend/scripts/init_mysql.sh

bash backend/scripts/migrate.sh
PYTHONPATH=backend python backend/run.py
```

另开终端启动前端：

```bash
cd frontend
npm run dev
```

前端默认访问 `http://127.0.0.1:8000/api/v1`，可在 `.env` 中通过 `VITE_API_BASE_URL` 覆盖（前端目录下的 `.env.local` 也支持该变量）。后端健康检查地址为 `http://127.0.0.1:8000/api/v1/health`。

## Docker 开发

确认外部网络存在（脚手架不会自动创建同名网络）：

```bash
docker network inspect ai_tag_fix_default
cp .env.docker.example .env
docker compose up --build
```

Compose 只包含 `backend` 和 `frontend`，通过已有 `ai_tag_fix_default` 网络访问 `ai_tag_fix_mysql` 和 `ai_tag_fix_redis`。如现有容器使用不同名称，可在运行前设置 `DOCKER_MYSQL_HOST` 和 `DOCKER_REDIS_HOST`。

## 数据隔离约束

- `MYSQL_DATABASE` 不是 `dawenzhang` 时，后端配置加载即失败。
- Alembic 在线迁移会再次执行 `SELECT DATABASE()` 校验，目标不是 `dawenzhang` 时拒绝迁移。
- Redis 客户端固定使用 db1；缓存 key 统一为 `dawenzhang:*`。
- 缓存清理使用 `SCAN` + 项目前缀删除，绝不调用 `FLUSHDB` 或 `FLUSHALL`。
- `init_mysql.sh` 只执行幂等的建库、建用户和授权，不包含删除、重置或修改 `ai_tag_fix` 的 SQL。

如需清理项目缓存，执行 `make clear-cache`；该命令只删除 db1 中的 `dawenzhang:*` key。

## 基础验证

```bash
PYTHONPATH=backend python -m pytest backend/tests
cd frontend && npm run test
```

初始化入口使用项目的 PyMySQL 依赖，不要求额外安装 `mysql` CLI。
