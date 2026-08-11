# AgentShield

AgentShield 是面向企业 Agent/RAG 系统的 LLM 安全网关、模型调用评测与请求审计平台。

项目重点不是只调用模型，而是验证模型调用过程中的安全边界：请求是否成功、模型是否拒绝、服务是否失败或超时，以及这些结果能否被安全地记录和追踪。

## 当前状态

当前已完成阶段 0～7。已完成内容包括：

- Python 项目环境和 FastAPI 健康检查接口；
- Git 本地版本记录和 GitHub 远程仓库交付；
- Docker Compose 管理的 PostgreSQL 开发库和测试库；
- 请求审计记录的保存、读取和基础错误处理；
- 可替换的模型调用结构和 Mock 模型（只用于测试的模拟模型服务）；
- 统一的 `ModelProvider` 协议、Provider 注入和 Provider 工厂；
- `OpenAIModelProvider` 真实 Provider 骨架、默认 HTTP 调用函数和假 HTTP 测试替身；
- 模型正常、拒绝、失败、超时、格式错误和未知场景的测试；
- 审计摘要不保存完整 Prompt 或完整模型回答；
- Mock 专用的 `/model/test` 与正式 `/model/call` 接口已分离；
- `/model/test` 强制使用 Mock，不受本机真实 Provider 配置影响；
- 重复 `request_id` 会在调用 Provider 前被拒绝，避免顺序重试重复产生模型费用；
- 已使用 APINebula 第三方 OpenAI 兼容服务成功完成一次真实模型调用和安全审计验证。
- `/model/test`、`/model/call` 和审计查询接口均要求 AgentShield API Key；
- 缺少、错误或停用的 Key 分别被安全拒绝；
- 模型调用的租户由认证结果确定，不信任请求体提交的 `tenant_id`；
- 审计记录只能由所属租户读取，跨租户查询统一返回 `404`；
- 响应和审计记录不保存完整 API Key。

当前最近一次阶段 7 自动测试记录为：

```text
71 passed
```

自动测试只使用 Mock 和假 HTTP，不会访问真实模型或消耗模型费用。阶段 7 的人工验收已使用 Mock 验证：认证租户可调用并读取自己的审计记录，另一租户读取同一记录得到 `404`。

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

阶段 6 模型配置名称如下：

```dotenv
AGENTSHIELD_MODEL_PROVIDER=mock
AGENTSHIELD_MODEL_API_KEY=
AGENTSHIELD_MODEL_NAME=gpt-5.6-terra
AGENTSHIELD_MODEL_BASE_URL=https://api.openai.com/v1
```

`.env.example` 默认使用 Mock，避免意外联网或产生费用。人工验证第三方兼容服务时，只在本机 `.env` 中设置 `real`、实际模型名称、服务地址和该服务签发的 Key。不得把一家服务的 Key 交给另一家服务。

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

模型接口和审计查询接口：

```text
POST http://127.0.0.1:8000/model/test
POST http://127.0.0.1:8000/model/call
GET  http://127.0.0.1:8000/audit/{request_id}
```

三个接口都需要 `X-API-Key` 请求头。`/model/test` 只使用 Mock，请求中需要 `scenario`。`/model/call` 不接收 `scenario`，并通过本机配置选择正式 Provider。请求体中的 `tenant_id` 不作为租户依据；服务只使用 API Key 认证得到的租户。

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

两个接口都返回模型状态、回答内容和错误码，并把不含完整 Prompt 或完整回答的审计摘要保存到 PostgreSQL。

### 真实模型人工验证

以下操作会访问外部服务并可能产生费用，不得放入日常自动测试。

1. 在本机 `.env` 中填写兼容服务的真实配置，不要把 Key 写入命令、截图、README 或 Git。
2. 启动开发数据库，并使用 `pg_isready` 确认显示 `accepting connections`。
3. 启动 FastAPI：

```powershell
python -m uvicorn app.main:app
```

4. 打开 `http://127.0.0.1:8000/docs`，只对 `/model/call` 使用全新的 `request_id` 执行一次无敏感信息的短请求。
5. 确认响应为 HTTP `200`、`status=success`、`error_code=null`。
6. 查询同一 `request_id` 的审计记录，确认 `summary=model_status=success`、摘要哈希长度为 `64`，且没有完整 Prompt、完整回答或 Key。
7. 验证后使用 `Ctrl+C` 停止 FastAPI，防止误操作重复调用。

2026-08-10 已使用 APINebula 第三方 OpenAI 兼容服务进行一次人工验证：

- 模型：`gpt-5.6-terra`；
- 请求编号：`req-apinebula-real-003`；
- 接口响应：HTTP `200`、`status=success`、`error_code=null`；
- 审计记录：`status=success`、`summary=model_status=success`、`summary_hash` 长度 `64`；
- 服务层记录的调用耗时：`5856 ms`；
- 安全检查：响应、审计摘要和 Git 状态未显示完整 Key；`.env` 仍被 Git 忽略。

本次人工验证前如实记录了两个失败现象：

- 令牌使用不匹配的用户分组时，第三方服务返回 HTTP `503`，AgentShield 保存了 `MODEL_API_HTTP_503` 失败审计；
- 调整为可用的 Codex 分组后，重复使用已存在的 `request_id` 导致模型调用后审计保存失败并返回本地 HTTP `500`。已增加服务层前置重复检查，避免顺序重试再次调用 Provider。

## 运行测试

启动测试数据库后，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

阶段7当前验证结果：

```text
71 passed
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

### 阶段6：Mock 与真实模型调用闭环

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
- 当前自动测试记录：`54 passed`；
- 日常自动测试不读取本机真实 Provider 配置、不访问网络且不消耗模型费用；
- 已使用 APINebula 第三方兼容服务成功执行一次真实模型请求；
- 真实回答经服务层和正式接口返回，并生成不含完整 Prompt、完整回答或 Key 的审计记录；
- `/model/test` 已强制使用 Mock，重复 `request_id` 已在 Provider 调用前检查。

### 阶段7：API Key 认证和基础用户隔离

- 从本机 `.env` 的 `AGENTSHIELD_API_KEY_RECORDS` 读取 API Key、租户和启用状态；配置示例保持空列表，不含真实 Key；
- `/model/test`、`/model/call` 和 `GET /audit/{request_id}` 都要求 `X-API-Key`；
- 缺少或错误的 Key 返回 `401`，停用的 Key 返回 `403`；
- 模型调用和审计保存使用认证得到的租户，不使用请求体伪造的 `tenant_id`；
- 审计查询在数据库中同时按 `request_id` 和认证租户筛选，跨租户和不存在的记录统一返回 `404`；
- 响应与审计记录不保存完整 Key；当前应用尚未实现日志写入；
- 自动测试验证了认证、租户覆盖、跨租户隔离和 Key 不进入响应或审计记录；当前自动测试结果：`71 passed`；
- 已完成人工 Mock 验收：alpha 租户成功调用并读取自己的审计记录，beta 租户查询同一记录得到 `404`。

## 阶段 6～12 路线图

### 阶段6：Mock 与真实模型调用闭环

- 保留可重复、无费用的 Mock 自动测试；
- 从本机 `.env` 读取真实模型配置，真实密钥不进入代码和 Git；
- 成功完成一次真实模型请求；
- 验证真实回答经过服务层返回并生成脱敏审计记录；
- 将 Mock 专用场景与正式模型接口分离；
- 日常自动测试不访问真实模型、不消耗模型费用。

### 阶段7：API Key 认证和基础用户隔离

- 请求必须携带 AgentShield API Key；
- 缺少、错误或停用的 Key 被拒绝；
- 从认证结果确定租户；
- 不同租户不能读取彼此的审计记录；
- 响应、日志和数据库不保存完整 Key。

### 阶段8：Prompt、PII、工具和 SSRF 安全检查

- 按 Prompt Injection、PII、工具允许名单、URL/SSRF 的顺序逐个实现；
- 高风险请求在调用模型或工具前被阻止；
- 检测结果和阻止原因进入审计记录；
- 记录规则的误报、漏报和已知限制；
- 不把简单关键词匹配描述成完整安全方案。

### 阶段9：攻击评测系统和量化结果

- 在 `evals/` 中建立结构统一的安全样例；
- 从 30 条可检查样例逐步扩充到 50～100 条；
- 一条命令批量执行评测；
- 统计正确结果、误报、漏报和检测耗时；
- 输出可重复的 JSON 或 CSV 报告；
- 分析至少三个失败样例。

### 阶段10：Redis 限流、日志和统一错误处理

- 按 API Key 或租户限制单位时间请求数量；
- 不同租户分别计数；
- 统一错误格式和请求追踪编号；
- 明确 Redis 不可用时的行为；
- 日志不记录完整 Key、完整 Prompt 和数据库密码。

### 阶段11：Docker、数据库迁移和压力测试

- 使用 Docker Compose 启动 FastAPI、PostgreSQL 和 Redis；
- 使用 Alembic 管理数据库表结构升级和回滚；
- 在干净环境中重复验证启动步骤；
- 执行一次固定参数、可重复的基础压力测试；
- 如实记录延迟、吞吐量、错误和实际发现的性能问题。

### 阶段12：看板、部署、文档和求职材料

- 使用简单看板展示风险和审计数据；
- 准备三分钟项目演示；
- 完善 README、架构图、设计取舍和已知限制；
- 部署可演示版本，或者提供经过验证的本地演示；
- 完成密钥检查、简历项目描述和面试问题整理。

## 安全边界

- 真实模型 API Key 只允许保存在本机 `.env`、部署平台环境变量或秘密管理系统；
- 不在源代码、测试、命令、截图、日志或文档中写数据库密码或真实密钥；
- `.env` 不提交到 GitHub；
- 不把完整 Prompt 或完整模型回答写入审计摘要；
- 测试数据库与开发数据库分开；
- 错误信息不应返回数据库密码、连接字符串或其他敏感配置；
- 未经授权不得对外扫描、攻击或访问第三方系统。

## 当前限制与后续计划

当前项目是经过测试、可追踪交付的最小实现，不应直接包装成完整生产系统。尚未完成：

- 官方 OpenAI API 的实际连通性验证；当前只验证了 APINebula 第三方兼容服务；
- Alembic 数据库迁移、升级和回滚；
- OAuth、企业单点登录、角色权限和更完整的多租户隔离；
- Prompt Injection、PII、工具和 SSRF 基础安全检查；
- 可重复的攻击评测数据集和量化报告；
- Redis 限流、统一错误和安全日志；
- 高并发压测、连接池调优和故障恢复；
- 监控、告警、数据库备份和灾难恢复；
- 看板、部署验证和求职演示材料。

## 开发约定

- 先明确功能规则，再编写测试，再实现最少代码；
- 每次只修改一个小功能，修改后先运行相关测试，再运行全部测试；
- 测试数量不是进度指标；测试必须对应明确行为、安全边界或已经发生的错误；
- 相同场景不在 Provider、服务和接口三层机械重复，优先合并结构相同的测试；
- 日常自动测试不访问真实模型、不消耗模型费用，真实联网验证单独执行并记录；
- 测试失败时先阅读完整错误并判断原因，不直接重写大量代码；
- README 只描述已经实际验证的内容；
- 未经确认不执行 `git add`、`git commit` 或 `git push`；
- 任何提交前都要检查敏感文件、差异和测试结果。
