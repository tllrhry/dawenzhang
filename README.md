# 大文章智能分类 MVP 基础骨架

项目保留 React + TypeScript + Vite 前端和 Python + FastAPI 后端，面向 2 核 4GB Ubuntu 演示服务器采用单机运行：SQLite 保存业务数据，本地目录保存上传和导出文件，模型能力通过外部 API 调用。当前不包含 Word 解析、判定规则、模型调用或 Excel 导出的业务实现。

## 前置条件

- Python 3.12+
- Node.js 22+ 和 npm（本地开发）
- Docker Compose（Ubuntu 演示部署）

不需要 MySQL、Redis、RabbitMQ、Milvus、MinIO 或本地模型服务。

## 宿主机开发

```bash
cp .env.example .env
# 按需编辑 .env 中的 SQLite 路径和外部 AI API 配置
python -m pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..

bash backend/scripts/migrate.sh
PYTHONPATH=backend python backend/run.py
```

另开终端启动前端：

```bash
cd frontend
npm run dev
```

本地开发前端默认访问 `http://127.0.0.1:8000/api/v1`；生产构建使用同域的 `/api/v1`。后端健康检查地址为 `http://127.0.0.1:8000/api/v1/health`。

## Ubuntu 演示部署

在服务器上执行：

```bash
cp .env.docker.example .env
# 填写 AI_BASE_URL、AI_API_KEY；生产时设置 HTTP_PORT=80
docker compose up --build
```

Compose 只启动 FastAPI 和用于生产静态构建的 Nginx 前端容器。后端端口不暴露到公网；Nginx 代理 `/api/` 并限制请求体为 10MB。`APP_DATA_DIR`（默认 `./data`）持久化 SQLite 数据库、上传文件和导出文件，容器重建前应备份整个目录。

公网演示应在 Nginx 前配置 HTTPS 终止（例如宿主机 Nginx、Caddy 或云负载均衡），并仅开放 `80/443`；不要公开容器内部的数据库文件或后端端口。

## 运行约束

- `DATABASE_URL` 仅接受 SQLite；演示后端固定为单 worker，不支持并发写入扩展。
- 模型仅通过 `AI_BASE_URL` 和 `AI_API_KEY` 访问外部 API；未配置时应用仍可启动。
- `AI_CONNECT_TIMEOUT_SECONDS` 和 `AI_READ_TIMEOUT_SECONDS` 控制后续模型请求的超时边界。

## 基础验证

```bash
PYTHONPATH=backend python -m pytest backend/tests
cd frontend && npm run test
```
