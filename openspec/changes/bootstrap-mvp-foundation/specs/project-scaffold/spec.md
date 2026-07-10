## ADDED Requirements

### Requirement: 前后端基础骨架
项目 SHALL 提供可独立启动的前端和后端基础目录，前端使用 React + TypeScript + Vite，后端使用 Python + FastAPI。

#### Scenario: 启动后端开发服务
- **WHEN** 开发者按项目文档安装依赖并启动后端
- **THEN** 后端服务 SHALL 启动并提供版本化 API 根路径

#### Scenario: 启动前端开发服务
- **WHEN** 开发者按项目文档启动前端
- **THEN** 前端 SHALL 加载基础页面并能配置后端 API 地址

### Requirement: 基础健康检查
后端 SHALL 提供不依赖业务数据的健康检查接口，并分别反映应用、MySQL 和 Redis 的连接状态。

#### Scenario: 依赖均可用
- **WHEN** 应用、目标 MySQL 数据库和目标 Redis logical DB 均可连接
- **THEN** 健康检查 SHALL 返回成功状态及各依赖的可读状态

#### Scenario: 依赖不可用
- **WHEN** 任一必需依赖不可连接
- **THEN** 健康检查 SHALL 返回非成功状态，并指出失败的依赖，不得泄露密码或连接字符串中的敏感信息

### Requirement: 配置与敏感信息管理
项目 SHALL 通过环境变量或未提交的本地环境文件配置连接地址、数据库名、Redis logical DB、应用端口和 AI 接口，不得把真实凭据提交到代码仓库。

#### Scenario: 使用示例配置启动
- **WHEN** 开发者根据 `.env.example` 创建本地配置并填入有效连接信息
- **THEN** 前后端 SHALL 使用该配置启动，不要求修改源代码

#### Scenario: 检测错误数据库配置
- **WHEN** 数据库配置指向 `ai_tag_fix` 或其他非本项目数据库
- **THEN** 后端启动检查 SHALL 拒绝该配置或明确报告隔离校验失败
