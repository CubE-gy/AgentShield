# AgentShield

AgentShield 是一个面向 Agent/RAG 系统的 LLM 安全网关学习项目。它在请求进入模型前完成身份认证和基础安全检查，在调用后保存不含完整 Prompt、回答和密钥的审计记录。

当前版本用于学习、面试展示和本地验证，不应直接作为完整企业安全产品使用。

技术栈：Python、FastAPI、PostgreSQL、Redis、SQLAlchemy、Docker Compose、pytest。

## 当前能力

- 使用 AgentShield API Key 认证请求，并由认证结果确定租户；
- 不同租户不能读取彼此的审计记录；
- `/model/test` 使用 Mock（不访问真实模型的测试替代服务）；
- `/model/call` 通过 Provider（统一不同模型调用方式的适配层）访问配置的模型服务；
- 重复 `request_id` 在模型调用前被拒绝，避免顺序重试重复产生费用；
- 在模型调用前执行 Prompt Injection、PII、工具允许名单和 URL/SSRF 基础检查；
- 邮箱和中国大陆手机号脱敏后再发送给模型；
- 将模型状态、安全风险和处理动作写入 PostgreSQL 审计记录；
- 按认证后的租户使用 Redis 限流，默认每 60 秒最多 60 次模型请求；
- 为每个请求返回追踪编号，并记录不含 API Key、Prompt 和模型回答的安全日志；
- 统一返回安全错误格式，明确请求是否可重试；
- 使用 50 条固定样例离线统计安全规则的误报、漏报、脱敏错误和耗时。

## 核心流程

```text
HTTP 请求
→ API Key 认证并确定租户
→ Redis 按认证租户限流
→ 创建数据库 Session 和 Provider
→ 检查重复 request_id
→ Prompt Injection 检查
→ 工具允许名单检查
→ URL/SSRF 检查
→ PII 脱敏
→ provider.call(prompt)
→ 生成脱敏审计记录
→ PostgreSQL
→ 返回带追踪编号的响应
```

前三类安全检查命中高风险时，不执行 `provider.call()`。PII 命中时替换敏感字段并继续调用。当前采用短路处理，因此一条请求只记录首先命中的阻止风险。

## 项目目录

```text
app/                    FastAPI、认证、模型调用、安全检查和审计代码
tests/                  自动测试
evals/                  离线安全评测样例、运行脚本和报告
evals/reports/          可重复的基准评测报告
evals/analysis.md       失败样例分析
scripts/                项目维护与验证脚本
load_tests/reports/     本机基础压力测试报告
Dockerfile              FastAPI 容器构建说明
docker-entrypoint.sh    容器启动前执行数据库迁移的脚本
compose.yaml            FastAPI、Redis、PostgreSQL 开发库和测试库
.dockerignore           Docker 打包时排除本机密钥与缓存的清单
.env.example            不含真实密钥的配置示例
requirements.txt        Python 依赖
AGENTS.md               Codex 开发与教学规则
```

## 快速启动

环境要求：Python 3.11+、Git、Docker Desktop。

### 1. 创建 Python 独立环境并安装依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 创建本机配置

```powershell
Copy-Item .env.example .env
```

`.env` 必须保留在本机，不能提交到 Git。至少需要配置开发库、测试库、Compose 数据库账号和一条启用的 AgentShield API Key：

```dotenv
AGENTSHIELD_DEV_DATABASE_URL=postgresql+psycopg://本机开发用户:本机开发密码@127.0.0.1:5432/agentshield_dev
AGENTSHIELD_TEST_DATABASE_URL=postgresql+psycopg://本机测试用户:本机测试密码@127.0.0.1:5433/agentshield_test

AGENTSHIELD_DEV_DB_USER=本机开发用户
AGENTSHIELD_DEV_DB_PASSWORD=本机开发密码
AGENTSHIELD_DEV_DB_NAME=agentshield_dev
AGENTSHIELD_TEST_DB_USER=本机测试用户
AGENTSHIELD_TEST_DB_PASSWORD=本机测试密码
AGENTSHIELD_TEST_DB_NAME=agentshield_test

AGENTSHIELD_API_KEY_RECORDS=[{"value":"替换为本机测试Key","tenant_id":"tenant-demo","is_active":true}]
AGENTSHIELD_ALLOWED_TOOLS=[]
AGENTSHIELD_REDIS_URL=redis://127.0.0.1:6379/0
AGENTSHIELD_RATE_LIMIT_MAX_REQUESTS=60
AGENTSHIELD_RATE_LIMIT_WINDOW_SECONDS=60
```

默认保持 `AGENTSHIELD_MODEL_PROVIDER=mock`，避免意外联网和产生费用。真实模型密钥只能填写在本机 `.env`。

### 3. 一条命令启动完整 Docker 服务

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

该命令会启动 FastAPI、Redis、开发 PostgreSQL 和测试 PostgreSQL。FastAPI 会等待开发 PostgreSQL 与 Redis 健康后，先自动执行 `alembic upgrade head`（将数据库结构升级到最新记录），再监听电脑的 `8000` 端口。

`docker compose ps` 预期显示 `agentshield-app`、`agentshield-redis`、`agentshield-postgres-dev` 和 `agentshield-postgres-test`。Redis 使用端口 `6379`，开发库使用端口 `5432`，测试库使用端口 `5433`。

### 4. 验证 FastAPI 与数据库迁移

```powershell
docker compose logs app
```

日志应显示 Alembic 已连接 PostgreSQL，随后 Uvicorn 启动。打开 `http://127.0.0.1:8000/docs` 使用 Swagger 页面，或访问健康检查：

```text
GET http://127.0.0.1:8000/health
```

预期结果：

```json
{"status":"ok"}
```

对于全新的数据库，首份迁移会创建 `audit_records` 表。对于旧项目已存在该表、但没有 Alembic 版本记录的数据库，必须先核对字段结构一致，再在项目根目录执行一次：

```powershell
.\.venv\Scripts\alembic.exe stamp head
```

`stamp`（标记）只写入迁移版本记录，不创建或删除表，也不修改审计数据。不要对字段结构未知的数据库直接执行该命令。

### 5. 停止与重启

```powershell
docker compose stop
docker compose up -d
```

`stop` 只停止容器，不删除 PostgreSQL 数据卷（Docker 保存数据库数据的持久存储位置）。正常重启后，迁移版本、审计表和审计数据应保留。不要在需要保留数据时执行 `docker compose down -v`，其中 `-v` 会删除数据卷。

## 核心接口

| 接口 | 用途 |
|---|---|
| `POST /model/test` | 固定使用 Mock，适合日常测试和人工演示 |
| `POST /model/call` | 使用本机配置的正式 Provider，可能访问外部模型并产生费用 |
| `GET /audit/{request_id}` | 查询当前认证租户自己的审计记录 |

三个接口都需要在请求头填写 `X-API-Key`。请求体中的 `tenant_id` 不作为租户依据。

`/model/test` 最小请求示例：

```json
{
  "request_id": "req-demo-001",
  "prompt": "请查询订单状态",
  "scenario": "success"
}
```

Mock 支持 `success`、`reject`、`failure`、`timeout` 和 `malformed` 场景。`tool_name` 与 `target_url` 是可选字段，只在对应安全检查中填写。

真实模型人工验证必须使用新的 `request_id` 和不含敏感信息的短 Prompt。项目曾使用 APINebula 的 OpenAI 兼容服务完成一次真实调用；这不代表已经验证所有模型服务商。

## 限流与错误响应

`/model/test` 与 `/model/call` 都按认证后的租户独立限流；请求体中的 `tenant_id` 不参与计数。超过次数时返回 HTTP `429` 和 `Retry-After` 响应头。Redis 不可用时采用 fail-closed（无法确认是否超限时拒绝请求）的策略，返回 HTTP `503`，请求不会继续创建 Provider 或调用模型。

所有预期错误与普通路由错误都使用以下结构，并在响应头返回同一个 `X-Request-Trace-Id`：

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "请求次数超过限制",
    "retryable": true,
    "trace_id": "本次请求的追踪编号"
  }
}
```

认证错误、请求格式错误、路由或方法错误不可重试；限流、Redis、数据库暂时不可用和未知内部错误可稍后重试。重复 `request_id` 不应原样重试，应更换编号或查询原记录。

## 验证项目

### 自动测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

自动测试使用 Mock、假 HTTP 和独立测试数据库，不主动调用真实模型。

最近一次完整自动测试结果：134 项通过，耗时 5.90 秒。

### 离线安全评测

```powershell
.\.venv\Scripts\python.exe evals\run_security_evals.py
```

pytest 用于检查已有代码行为是否被改坏；安全评测用于衡量阶段 8 规则在固定样例中的误报和漏报。两者不能用同一个“测试数量”描述。

当前评测集包含 50 条样例，使用固定 DNS 映射，不访问真实模型、数据库、外网或真实 DNS。基准结果为：

```text
44/50 通过
误报 1 条
漏报 4 条
脱敏错误 1 条
```

详细结果见 `evals/reports/`，失败原因见 `evals/analysis.md`。该结果只代表这 50 条固定样例，不能证明系统具备完整安全防护能力。

### 基础压力测试

压力测试使用固定的 20 个请求和 5 个并发请求，目标为本机 Docker 中的 `POST /model/test`。它只使用 Mock，不访问真实模型，但会写入开发数据库的审计记录。

先在本机 `.env` 中设置一条已启用的 AgentShield API Key：

```dotenv
AGENTSHIELD_LOAD_TEST_API_KEY=本机有效测试Key
```

确认 Docker 服务正在运行后，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_load_test.py
```

报告会保存到 `load_tests/reports/`，包含成功数、错误数、吞吐量、平均与最大延迟、测试环境、代码版本和限制说明；不保存 API Key、完整 Prompt 或模型回答。本机单次结果不能代表高并发生产能力。

压力测试报告会记录运行时的 Git 提交版本。完成代码提交后，应重新运行该命令并将对应版本的基准结果、实际观察和限制写入本节。

## 安全边界与已知限制

已经采取的保护：

- `.env`、真实密码和真实密钥不进入 Git；
- 响应和审计记录不保存完整 AgentShield API Key；
- 审计摘要不保存完整 Prompt 和完整模型回答；
- 模型调用前执行认证、重复请求检查和基础安全检查；
- 成功和已处理失败日志可通过追踪编号排查，不记录完整 API Key、Prompt、模型回答或数据库密码；
- Redis 不可用时阻止模型调用，避免限流失效导致意外费用；
- 安全评测不使用真实个人信息或不受控外部网络。

当前限制：

- Prompt Injection 使用有限的可解释规则，仍会误报和漏报；
- PII 只处理格式明确的邮箱和中国大陆手机号；
- 工具检查只验证名称，项目尚未执行真实工具；
- SSRF 预检查不能单独解决 DNS 重绑定和重定向，真实访问时仍需复检最终地址；
- API Key 使用本机静态配置，尚无哈希密钥库、自动轮换和复杂权限系统；
- 当前只验证过一家第三方 OpenAI 兼容服务；
- 当前限流采用固定时间窗口；窗口边界可能出现短时间突发，`Retry-After` 返回整个窗口秒数而非精确剩余秒数；
- 已完成一次固定 20 请求、5 并发的本机 Mock 压力测试；尚未进行高并发、长时间或真实模型压力测试；
- 尚未完成部署和监控。

## 阶段状态

| 阶段 | 状态 | 核心成果 |
|---|---|---|
| 0～4 | 已完成 | 环境、FastAPI、Git 和 GitHub 交付 |
| 5 | 已完成 | PostgreSQL 审计记录 |
| 6 | 已完成 | Mock 与真实模型调用闭环 |
| 7 | 已完成 | API Key 认证和租户隔离 |
| 8 | 已完成 | Prompt、PII、工具和 SSRF 基础检查 |
| 9 | 已完成 | 50 条离线安全评测、量化报告和失败分析 |
| 10 | 已完成 | Redis 租户限流、安全日志、请求追踪和统一错误处理 |
| 11 | 进行中 | Docker 完整启动、数据库迁移、重启数据保留和基础压力测试已验证；待提交和最终核对 |
| 12 | 未开始 | 看板、部署、文档和求职材料 |

完整阶段目标和开发规则以 `AGENTS.md` 为准，README 不重复保存开发过程。

## README 更新规则

一个功能只在一个位置详细说明；阶段结束时覆盖当前状态，不追加旧历史。只保留最近一次有效的测试或评测结果。

| 阶段 | 需要检查并更新的 README 模块 |
|---|---|
| 0 | 环境要求（仅在要求变化时） |
| 1 | 项目目录、快速启动、依赖 |
| 2 | 当前能力、核心流程、接口 |
| 3 | 通常不更新 |
| 4 | 阶段状态 |
| 5 | 当前能力、核心流程、目录、启动、安全边界 |
| 6 | 当前能力、流程、接口、模型配置和限制 |
| 7 | 当前能力、认证说明、安全边界、阶段状态 |
| 8 | 当前能力、安全流程、安全边界、阶段状态 |
| 9 | 验证项目、评测结果、安全限制、阶段状态 |
| 10 | 快速启动、限流与错误行为、安全边界、阶段状态 |
| 11 | 环境要求、快速启动、目录、验证方式和性能限制 |
| 12 | 项目简介、最终架构、部署、演示和最终能力边界 |
