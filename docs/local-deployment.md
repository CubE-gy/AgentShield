# AgentShield 本地部署与演示验收

## 当前部署状态

已验证：在 Windows 本机使用 Docker Compose 启动 AgentShield、Redis、开发 PostgreSQL 与测试 PostgreSQL，并由 App 在启动前自动执行 Alembic 数据库迁移。

未完成：公网部署、域名、HTTPS（加密的网页访问协议）、监控告警、自动备份、高可用和云端密钥管理。本项目当前是本地学习和演示版本，不应直接作为企业线上服务使用。

## 已验证环境

最近一次基础压力测试的环境为 Windows 11、Python 3.12.8、本机 Docker、Mock（假的替代服务）和代码提交 `c611132`。固定参数为 20 个请求、5 个并发请求；结果为 20 成功、0 错误、53.62 请求/秒，平均延迟 36.86 毫秒，最大延迟 71.16 毫秒。

这只是一次本机 Mock 测试，不能代表真实模型、长时间运行或高并发环境的性能。

## 启动步骤

在项目根目录执行：

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

这些命令的作用依次是：检查 Docker Compose 配置、构建并在后台启动服务、查看服务状态。

预期服务：

| 服务 | 本机端口 | 用途 |
|---|---:|---|
| `agentshield-app` | 8000 | FastAPI 接口、Swagger 与本地看板 |
| `agentshield-redis` | 6379 | 按租户限流 |
| `agentshield-postgres-dev` | 5432 | 开发审计记录 |
| `agentshield-postgres-test` | 5433 | 自动测试数据库 |

App 会等待开发 PostgreSQL 和 Redis 健康后，执行 `alembic upgrade head`（把数据库结构升级到最新迁移记录），然后监听 `8000` 端口。

## 演示验收

启动后依次访问：

| 地址 | 预期结果 |
|---|---|
| `http://127.0.0.1:8000/health` | 返回 `{"status":"ok"}` |
| `http://127.0.0.1:8000/docs` | Swagger 页面可用；可通过 **Authorize** 输入一次 API Key |
| `http://127.0.0.1:8000/dashboard` | 可输入 API Key，查看当前租户的汇总和最近 10 条审计记录 |

完整的正常请求、攻击阻止、PII（可以识别个人身份的敏感信息）脱敏和审计查询演示见 `docs/demo-guide.md`。

## 停止与重启

```powershell
docker compose stop
docker compose up -d
```

`stop` 只停止容器，不删除 PostgreSQL 数据卷（Docker 保存数据库数据的持久存储位置）。重启后，数据库迁移版本和审计记录应保留。

不要在需要保留数据时执行 `docker compose down -v`；其中 `-v` 会删除数据库数据卷。

## 安全检查清单

- `.env` 仅保留在本机，不能提交到 Git；
- 不在截图、日志、文档或请求示例中暴露完整 API Key；
- 本地演示优先使用 `/model/test`，它固定使用 Mock，不产生真实模型费用；
- `/model/call` 可能访问外部模型服务，只有填写真实配置并主动调用时才使用；
- 停止演示后，在 Swagger 点击 **Logout**，关闭包含 API Key 的页面。
