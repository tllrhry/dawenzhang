## ADDED Requirements

### Requirement: 独立 MySQL 数据库
项目 SHALL 复用现有 MySQL 8 实例，但必须使用独立的 `dawenzhang` 数据库和独立应用用户；应用不得使用 `ai_tag_fix` 数据库。

#### Scenario: 首次初始化数据库
- **WHEN** 管理员使用项目提供的初始化入口配置有效的 MySQL 管理凭据
- **THEN** 系统 SHALL 幂等创建 `dawenzhang` 数据库、utf8mb4 字符集设置和项目专用应用用户

#### Scenario: 应用连接目标数据库
- **WHEN** 后端使用项目应用用户建立数据库连接
- **THEN** 连接 SHALL 默认指向 `dawenzhang`，并且迁移表只出现在该数据库中

#### Scenario: 重复执行初始化
- **WHEN** 数据库初始化入口被执行多次
- **THEN** 已有 `dawenzhang` 数据库和应用用户 SHALL 保持不变，不得删除、重置或修改 `ai_tag_fix` 的表和数据

### Requirement: 隔离 Redis logical DB
项目 SHALL 复用现有 Redis 7 实例的 logical DB `1`，不得使用现有项目使用的 `db0`，并 SHALL 对本项目 key 统一增加 `dawenzhang:` 前缀。

#### Scenario: 建立 Redis 连接
- **WHEN** 后端初始化 Redis 客户端
- **THEN** 客户端 SHALL 选择 database index `1`，并使用配置的 host、port 和密码

#### Scenario: 写入项目缓存
- **WHEN** 项目写入缓存、会话或任务状态
- **THEN** key SHALL 以 `dawenzhang:` 开头，并写入 Redis `db1`

#### Scenario: 清理项目缓存
- **WHEN** 开发者执行项目缓存清理命令
- **THEN** 清理操作 SHALL 只作用于项目 key 或 `db1`，不得执行影响 `db0` 的全局 flush 操作

### Requirement: 复用基础设施而不重复编排
本项目的开发编排 SHALL 不定义或启动新的 MySQL、Redis 容器；连接方式 SHALL 同时支持宿主机运行和加入已有 Docker 网络的后端容器。

#### Scenario: 后端运行在宿主机
- **WHEN** 后端直接在宿主机启动
- **THEN** 配置 SHALL 支持通过 `127.0.0.1:3306` 和 `127.0.0.1:6379` 连接现有服务

#### Scenario: 后端运行在 Docker
- **WHEN** 后端以 Docker 容器运行
- **THEN** 项目编排 SHALL 支持加入已有的 `ai_tag_fix_default` 外部网络，并通过 `ai_tag_fix_mysql` 和 `ai_tag_fix_redis` 访问服务
