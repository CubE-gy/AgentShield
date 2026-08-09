# AgentShield

AgentShield 是面向企业 Agent/RAG 系统的 LLM 安全网关、模型调用评测与请求审计平台。

项目重点不是只调用模型，而是验证模型调用过程中的安全边界：请求是否成功、模型是否拒绝、服务是否失败或超时，以及这些结果能否被安全地记录和追踪。

## 当前状态

当前已完成阶段 0～6 的核心功能：

- Python 项目环境和 FastAPI 健康检查接口；
- Git 本地版本记录和 GitHub 远程仓库交付；
- Docker Compose 管理的 PostgreSQL 开发库和测试库；
- 请求审计记录的保存、读取和基础错误处理；
- 可替换的模型调用结构和 Mock 模型（只用于测试的模拟模型服务）；
- 统一的 `ModelProvider` 协议、Provider 注入和 Provider 工厂；
- `OpenAIModelProvider` 真实 Provider 骨架、默认 HTTP 调用函数和假 HTTP 测试替身；
- 模型正常、拒绝、失败、超时、格式错误和未知场景的测试；
- 审计摘要不保存完整 Prompt 或完整模型回答。

当前最近一次阶段6完整测试结果为：

```text
51 passed
```

本阶段尚未使用真实 API Key，也尚未发送真实模型网络请求；真实 Provider 已通过假 HTTP 覆盖正常响应、连接失败、超时、HTTP 错误和格式错误。

## 项目目标

- 统一接收 Agent 或模型调用请求；
- 对模型调用结果进行成功、拒绝、失败和超时分类；
- 对请求进行脱敏审计（去掉密码、API Key 等敏感内容后记录）；
- 为后续 Prompt Injection（提示词注入攻击）、RAG 越权和工具调用安全评测提供基础；
- 在不泄露完整 Prompt 的前提下支持问题排查和安全追踪。

## 技术栈与选型

- Python：主要开发语言。
- FastAPI：提供 HTTP 接口。
- PostgreSQL：保存审计记录，适合多人和多个请求同时访问；SQLite 只作为单机学习或临时测试方案。
- Docker Compose：通过配置文件启动和管理开发数据库、测试数据库。
- SQLAlchemy：使用 Python 定义数据表并执行数据库操作。
- psycopg：连接 PostgreSQL 的 Python 驱动。
- pydantic-settings：从 `.env` 读取应用配置。
- pytest：运行自动化测试。
- Git/GitHub：记录代码版本并进行远程交付。

## 项目目录

```text
app/                应用代码
tests/              自动化测试
evals/              安全评测样例目录
compose.yaml        PostgreSQL 开发库和测试库配置
requirements.txt    Python 依赖清单
.env.example        环境变量模板
.gitignore          Git 忽略规则
README.md           项目说明
AGENTS.md           Codex 协作和教学规则
```

## 环境要求

- Windows、macOS 或 Linux；
- Python 3.11 或更高版本；
- Docker Desktop（Windows 上需要 WSL 2 支持）；
- Git。

## 环境配置

在项目根目录创建本机配置文件：

```powershell
Copy-Item .env.example .env
```

`.env` 不得提交到 GitHub。当前 Compose 配置需要以下变量：

```dotenv
AGENTSHIELD_DEV_DATABASE_URL=postgresql+psycopg://agentshield:修改为本机开发密码@127.0.0.1:5432/agentshield_dev
AGENTSHIELD_TEST_DATABASE_URL=postgresql+psycopg://agentshield_test:修改为本机测试密码@127.0.0.1:5433/agentshield_test
AGENTSHIELD_DEV_DB_USER=agentshield
AGENTSHIELD_DEV_DB_PASSWORD=修改为本机开发密码
AGENTSHIELD_DEV_DB_NAME=agentshield_dev
AGENTSHIELD_TEST_DB_USER=agentshield_test
AGENTSHIELD_TEST_DB_PASSWORD=修改为本机测试密码
AGENTSHIELD_TEST_DB_NAME=agentshield_test
```

上面的密码只是占位说明，不能直接作为生产密码使用。真实配置放在本机 `.env`、生产秘密管理系统或部署平台环境变量中。

## 启动 PostgreSQL

在项目根目录执行：

```powershell
docker compose config --quiet
docker compose up -d
docker compose ps
```

开发库：电脑端口 `5432` → 容器内 PostgreSQL 端口 `5432`；测试库：电脑端口 `5433` → 容器内 PostgreSQL 端口 `5432`。

容器显示 `Running` 或 `Up` 只代表容器进程正在运行。确认数据库已准备好，可执行：

```powershell
docker exec agentshield-postgres-dev pg_isready
docker exec agentshield-postgres-test pg_isready
```

看到 `accepting connections` 才表示数据库已准备好接受连接。

## 启动 FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

访问 `GET http://127.0.0.1:8000/health`，预期返回：

```json
{"status": "ok"}
```

## API 使用示例

阶段6提供：

```text
POST http://127.0.0.1:8000/model/test
```

请求示例：

```json
{
  "request_id": "req-demo-001",
  "tenant_id": "tenant-demo",
  "agent_id": "agent-support",
  "prompt": "请查询订单状态",
  "scenario": "success"
}
```

支持场景：

| 场景 | 模拟结果 | 错误码 |
|---|---|---|
| `success` | 正常回答 | 无 |
| `reject` | 模型拒绝请求 | `MODEL_REFUSED` |
| `failure` | 模型服务不可用 | `MODEL_UNAVAILABLE` |
| `timeout` | 模型调用超时 | `MODEL_TIMEOUT` |
| `malformed` | 模型返回格式错误 | `MODEL_INVALID_RESPONSE` |
| 其他值 | 无效场景 | `MODEL_INVALID_SCENARIO` |

接口返回模型状态、回答内容和错误码，并把不含完整 Prompt 或完整回答的审计摘要保存到 PostgreSQL。

## 运行测试

启动测试数据库后，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

阶段6当前验证结果：

```text
51 passed
```

测试数据库使用端口 `5433`，测试代码不会主动操作开发数据库 `5432`。测试通过只代表已覆盖的场景符合预期，不代表已经完成高并发或完整生产部署。

## 阶段进度

### 阶段4：Git 与 GitHub 项目交付

- 使用 Git 保存项目版本；
- 创建 GitHub 私有仓库并配置远程地址；
- 完成本地提交和 GitHub 推送；
- 使用 `.gitignore` 排除 `.env`、`.venv/`、Python 缓存和 IDE 配置；
- 验证本地最新提交与远程分支同步；
- 未上传 `.env`、真实密码、真实 API Key 或缓存目录。

### 阶段5：PostgreSQL 请求审计记录

- 选择 PostgreSQL 作为正式数据库，未接入 SQLite；
- 使用 Docker Compose 创建独立开发库和测试库；
- 使用不同端口和数据卷隔离两套数据库；
- 使用 SQLAlchemy 和 psycopg 保存、读取审计记录；
- 对 `request_id` 设置唯一约束，重复编号会被拒绝；
- 处理记录不存在和数据库不可用等基础错误；
- 保存请求编号、租户、Agent、时间、状态、错误码、耗时、脱敏摘要和摘要哈希；
- 阶段5验证结果：`7 passed`；
- 当前表结构仍使用 `Base.metadata.create_all()`，尚未使用 Alembic（数据库表结构版本管理工具）。

### 阶段6：Mock 模型调用与审计流程

- 建立模型服务调用和 Mock Provider（模型服务适配层）结构；
- 模拟正常返回、拒绝、服务失败、超时和格式错误；
- 未知场景返回 `MODEL_INVALID_SCENARIO`；
- FastAPI 的 `/model/test` 调用服务层，不在路由中写死回答；
- 模型结果和脱敏审计摘要一起保存到 PostgreSQL；
- 测试验证 Prompt 和完整模型回答不会进入审计摘要；
- 定义统一的 `ModelProvider` 协议：`call(prompt) -> ModelResult`；
- Mock 场景保存在 `MockModelProvider` 创建参数中，不进入通用 Provider 调用签名；
- 服务函数支持从外部注入 Provider；
- 增加 `OpenAIModelProvider` 骨架；
- 真实 Provider 支持默认 HTTP 调用函数和可注入的测试替身；
- 配置 `AGENTSHIELD_MODEL_PROVIDER=mock` 时使用 Mock；
- 配置 `AGENTSHIELD_MODEL_PROVIDER=real` 时选择真实 Provider；
- 没有 API Key 时返回 `MODEL_API_KEY_MISSING`，不会发送网络请求；
- 假 HTTP 测试已覆盖正常响应、连接失败、超时、HTTP 错误和格式错误；
- 阶段6验证结果：`51 passed`；
- 本阶段尚未使用真实 API Key，也尚未执行真实模型请求。

## 安全边界

- 不使用真实模型 API Key；
- 不在源代码中写数据库密码或真实密钥；
- `.env` 不提交到 GitHub；
- 不把完整 Prompt 或完整模型回答写入审计摘要；
- 测试数据库与开发数据库分开；
- 错误信息不应返回数据库密码、连接字符串或其他敏感配置；
- 未经授权不得对外扫描、攻击或访问第三方系统。

## 当前限制与后续计划

当前项目是经过测试、可追踪交付的最小实现，不应直接包装成完整生产系统。尚未完成：

- 真实模型 API 的实际连通性验证和正式供应商切换；
- Alembic 数据库迁移、升级和回滚；
- 用户认证、权限和完整多租户隔离；
- Redis 限流和消息队列；
- 高并发压测、连接池调优和故障恢复；
- 监控、告警、数据库备份和灾难恢复；
- Prompt Injection、RAG 越权和工具调用安全评测的完整规则集。

## 开发约定

- 先明确功能规则，再编写测试，再实现最少代码；
- 每次只修改一个小功能，修改后先运行相关测试，再运行全部测试；
- 测试失败时先阅读完整错误并判断原因，不直接重写大量代码；
- README 只描述已经实际验证的内容；
- 未经确认不执行 `git add`、`git commit` 或 `git push`；
- 任何提交前都要检查敏感文件、差异和测试结果。
