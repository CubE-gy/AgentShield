"""对本机 Mock 模型接口执行固定参数的基础压力测试。"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

from dotenv import load_dotenv
import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIRECTORY = PROJECT_ROOT / "load_tests" / "reports"
REQUEST_COUNT = 20
CONCURRENCY = 5
REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class RequestResult:
    """单次压力测试请求的安全摘要。"""

    success: bool
    latency_ms: float
    error_type: str | None


def get_api_key() -> str:
    """读取仅用于压力测试的本机 API Key。"""

    api_key = os.getenv("AGENTSHIELD_LOAD_TEST_API_KEY")
    if not api_key:
        raise RuntimeError(
            "缺少 AGENTSHIELD_LOAD_TEST_API_KEY，无法执行压力测试"
        )
    return api_key


def get_git_revision() -> str:
    """读取当前代码版本；无法读取时保留明确标记。"""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def create_http_client() -> httpx.Client:
    """创建不继承系统代理设置的本地测试客户端。"""

    return httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False)


def send_request(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    request_id: str,
) -> RequestResult:
    """发送一条不含敏感数据的 Mock 模型请求。"""

    started_at = perf_counter()
    try:
        response = client.post(
            f"{base_url}/model/test",
            headers={"X-API-Key": api_key},
            json={
                "request_id": request_id,
                "prompt": "请返回订单状态。",
                "scenario": "success",
            },
        )
    except httpx.HTTPError as error:
        return RequestResult(
            success=False,
            latency_ms=(perf_counter() - started_at) * 1000,
            error_type=type(error).__name__,
        )

    return RequestResult(
        success=response.is_success,
        latency_ms=(perf_counter() - started_at) * 1000,
        error_type=None if response.is_success else f"http_{response.status_code}",
    )


def build_report(
    *,
    results: list[RequestResult],
    elapsed_seconds: float,
    request_count: int,
    concurrency: int,
    base_url: str,
    git_revision: str,
) -> dict[str, object]:
    """汇总不含敏感请求内容的压力测试结果。"""

    success_count = sum(result.success for result in results)
    error_types = Counter(
        result.error_type for result in results if result.error_type is not None
    )
    latencies = [result.latency_ms for result in results]
    error_count = len(results) - success_count

    observation = (
        "本次固定参数下未发现请求错误；未进行性能瓶颈分析。"
        if error_count == 0
        else f"首次发现的问题：出现 {error_count} 个请求错误。"
    )

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "base_url": base_url,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "git_revision": git_revision,
        },
        "parameters": {
            "request_count": request_count,
            "concurrency": concurrency,
        },
        "results": {
            "success_count": success_count,
            "error_count": error_count,
            "throughput_requests_per_second": round(
                len(results) / elapsed_seconds, 2
            ),
            "latency_ms": {
                "average": round(sum(latencies) / len(latencies), 2),
                "maximum": round(max(latencies), 2),
            },
            "error_types": dict(error_types),
        },
        "limitations": (
            "仅在本机以 20 请求、5 并发执行；结果不能代表高并发生产能力。"
        ),
        "observation": observation,
    }


def run_load_test(base_url: str, api_key: str) -> dict[str, object]:
    """以固定请求数与并发数执行测试并返回报告。"""

    run_id = uuid4().hex
    started_at = perf_counter()
    with create_http_client() as client:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            results = list(
                executor.map(
                    lambda index: send_request(
                        client,
                        base_url,
                        api_key,
                        f"load-{run_id}-{index:03d}",
                    ),
                    range(REQUEST_COUNT),
                )
            )

    return build_report(
        results=results,
        elapsed_seconds=perf_counter() - started_at,
        request_count=REQUEST_COUNT,
        concurrency=CONCURRENCY,
        base_url=base_url,
        git_revision=get_git_revision(),
    )


def main() -> None:
    """读取本机配置、执行测试并保存 JSON 报告。"""

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = get_api_key()
    base_url = os.getenv("AGENTSHIELD_LOAD_TEST_BASE_URL", DEFAULT_BASE_URL).rstrip(
        "/"
    )
    report = run_load_test(base_url, api_key)

    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIRECTORY / (
        f"load-test-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"压力测试报告：{report_path}")


if __name__ == "__main__":
    main()
