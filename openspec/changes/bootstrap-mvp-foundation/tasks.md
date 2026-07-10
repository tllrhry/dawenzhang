## 1. 项目骨架

- [x] 1.1 创建 `backend/` FastAPI 应用目录、依赖清单和本地启动入口
- [x] 1.2 创建 `frontend/` React + TypeScript + Vite 应用目录、依赖清单和本地启动入口
- [x] 1.3 建立后续业务模块目录：API、领域模型、服务、基础设施、数据和测试
- [x] 1.4 增加 `.env.example`、本地配置说明和敏感文件忽略规则

## 2. MySQL 隔离与迁移

- [x] 2.1 编写幂等的 MySQL 初始化脚本，创建 `dawenzhang` 数据库、utf8mb4 设置和专用应用用户
- [x] 2.2 增加 SQLAlchemy 数据库连接配置，并拒绝连接到 `ai_tag_fix` 数据库
- [x] 2.3 增加 Alembic 初始迁移配置和迁移执行入口
- [x] 2.4 增加数据库连接健康检查和目标数据库验证

## 3. Redis 隔离

- [x] 3.1 增加 Redis 客户端配置，默认选择 logical DB `1`
- [x] 3.2 实现统一的 `dawenzhang:` key 前缀和项目级缓存清理入口
- [x] 3.3 增加 Redis PING、database index 和读写隔离检查
- [x] 3.4 验证不会执行影响 `db0` 的全局清理操作

## 4. 应用健康检查与开发编排

- [x] 4.1 提供版本化后端健康检查 API，返回应用、MySQL 和 Redis 状态
- [x] 4.2 创建仅编排前后端的开发配置，不声明新的 MySQL 或 Redis 服务
- [x] 4.3 支持宿主机连接和加入已有 `ai_tag_fix_default` Docker 网络两种配置
- [x] 4.4 增加前端基础页面和后端 API 地址配置验证

## 5. 验证与交付

- [x] 5.1 在现有 MySQL 实例中验证 `dawenzhang` 数据库和应用用户初始化
- [x] 5.2 验证迁移只写入 `dawenzhang`，不修改 `ai_tag_fix`
- [x] 5.3 验证 Redis 数据写入 db1 且 key 带 `dawenzhang:` 前缀，db0 数据不受影响
- [x] 5.4 更新项目启动文档并运行前后端基础测试
