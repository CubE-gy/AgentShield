# AgentShield

AgentShield 是一个面向 Agent/RAG 系统的 LLM 安全网关学习项目。它在请求进入模型前完成身份认证和基础安全检查，在调用后保存不含完整 Prompt、回答和密钥的审计记录。

当前版本用于学习、面试展示和本地验证，不应直接作为完整企业安全产品使用。

技术栈：Python、FastAPI、PostgreSQL、SQLAlchemy、Docker Compose、pytest。

## 当前能力

- 使用 AgentShield API Key 认证请求，并由认证结果确定租户；
- 不同租户不能读取彼此的审计记录；
- `/model/test` 使用 Mock（不访问真实模型的测试替代服务）；
- `/model/call` 通过 Provider（统一不同模型调用方式的适配层）访问配置的模型服务；
- 重复 `request_id` 在模型调用前被拒绝，避免顺序重试重复产生费用；
- 在模型调用前执行 Prompt Injection、PII、工具允许名单和 URL/SSRF 基础检查；
- 邮箱和中国大陆手机号脱敏后再发送给模型；
- 将模型状态、安全风险和处理动作写入 PostgreSQL 审计记录；
- 使用 50 条固定样例离线统计安全规则的误报、漏报、脱敏错误和耗时。

## 核心流程

```text
HTTP 请求
→ API Key 认证并确定租户
→ 创建数据库 Session 和 Provider
→ 检查重复 request_id
→ Prompt Injection 检查
→ 工具允许名单检查
→ URL/SSRF 检查
→ PII 脱敏
→ provider.call(prompt)
→ 生成脱敏审计记录
→ PostgreSQL
```

前三类安全检查命中高风险时，不执行 `provider.call()`。PII 命中时替换敏感字段并继续调用。当前采用短路处理，因此一条请求只记录首先命中的阻止风险。

## 项目目录

```text
app/                    FastAPI、认证、模型调用、安全检查和审计代码
tests/                  自动测试
evals/                  离线安全评测样例、运行脚本和报告
evals/reports/          可重复的基准评测报告
evals/analysis.md       失败样例分析
compose.yaml            PostgreSQL 开发库和测试库
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
```

默认保持 `AGENTSHIELD_MODEL_PROVIDER=mock`，避免意外联网和产生费用。真实模型密钥只能填写在本机 `.env`。

### 3. 启动 PostgreSQL

```powershell
docker compose config --quiet
docker compose up -d
docker compose ps
```

开发库使用端口 `5432`，测试库使用端口 `5433`。

### 4. 启动 FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs` 使用 Swagger 页面，或访问健康检查：

```text
GET http://127.0.0.1:8000/health
```

预期结果：

```json
{"status":"ok"}
```

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

## 验证项目

### 自动测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

自动测试使用 Mock、假 HTTP 和独立测试数据库，不主动调用真实模型。

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

## 安全边界与已知限制

已经采取的保护：

- `.env`、真实密码和真实密钥不进入 Git；
- 响应和审计记录不保存完整 AgentShield API Key；
- 审计摘要不保存完整 Prompt 和完整模型回答；
- 模型调用前执行认证、重复请求检查和基础安全检查；
- 安全评测不使用真实个人信息或不受控外部网络。

当前限制：

- Prompt Injection 使用有限的可解释规则，仍会误报和漏报；
- PII 只处理格式明确的邮箱和中国大陆手机号；
- 工具检查只验证名称，项目尚未执行真实工具；
- SSRF 预检查不能单独解决 DNS 重绑定和重定向，真实访问时仍需复检最终地址；
- API Key 使用本机静态配置，尚无哈希密钥库、自动轮换和复杂权限系统；
- 当前只验证过一家第三方 OpenAI 兼容服务；
- 尚未完成 Redis 限流、Alembic 数据库迁移、压力测试、部署和监控。

## 阶段状态

| 阶段 | 状态 | 核心成果 |
|---|---|---|
| 0～4 | 已完成 | 环境、FastAPI、Git 和 GitHub 交付 |
| 5 | 已完成 | PostgreSQL 审计记录 |
| 6 | 已完成 | Mock 与真实模型调用闭环 |
| 7 | 已完成 | API Key 认证和租户隔离 |
| 8 | 已完成 | Prompt、PII、工具和 SSRF 基础检查 |
| 9 | 已完成 | 50 条离线安全评测、量化报告和失败分析 |
| 10 | 未开始 | Redis 限流、日志和统一错误处理 |
| 11 | 未开始 | Docker 完整启动、数据库迁移和压力测试 |
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
