# AgentShield

AgentShield 是面向企业 Agent/RAG 系统的 LLM 安全网关、攻击评测与审计平台。

## 当前状态

项目已完成第 0～3 步：环境检查、Python 独立环境、最简单的 FastAPI 健康检查接口，以及第一次本地 Git 保存。

当前正在进行第 4 步：检查 GitHub 上传前条件。暂未配置远程仓库，也未上传代码。

## 目录

- `app/`：程序代码
- `tests/`：自动测试代码
- `docs/`：设计和学习笔记
- `evals/`：安全测试样例

## 启动测试

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

成功时应看到全部测试通过，例如 `2 passed`。

## 启动开发服务

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

然后访问 <http://127.0.0.1:8000/health>，应返回：

```json
{"status":"ok"}
```

## 配置安全

`.env.example` 只放配置名称；本机真实配置应放在 `.env` 中。`.env` 已加入 `.gitignore`，不会被 Git 保存。
