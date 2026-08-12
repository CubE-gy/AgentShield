"""离线运行 AgentShield 的基础安全规则评测。

运行：.\\.venv\\Scripts\\python.exe evals\\run_security_evals.py
默认报告：.tmp/security_eval_report.json（不提交到 Git）。
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from math import ceil
import platform
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.security_checks import (
    SecurityCheckInput,
    check_prompt_injection,
    check_tool_allowlist,
    check_url_ssrf,
    mask_pii,
)
from evals.case_validation import validate_eval_data


DEFAULT_CASES_PATH = Path(__file__).with_name("security_cases.json")
DEFAULT_REPORT_PATH = PROJECT_ROOT / ".tmp" / "security_eval_report.json"
RULE_LIMITATIONS = (
    "提示注入仅识别少量可解释的覆盖指令模式，可能漏掉同义改写、编码和间接攻击。",
    "PII 目前仅按明确格式处理邮箱和中国大陆手机号，不识别地址等其他敏感信息。",
    "工具检查仅验证工具名称，不验证工具参数、权限或实际工具执行边界。",
    "SSRF 检查在评测中使用固定 DNS；真实网络请求仍需在连接前处理重定向和 DNS 重绑定风险。",
)


def run_evaluation(
    cases_path: Path = DEFAULT_CASES_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    dns_answers: dict[str, list[str]] | None = None,
    validate_cases: bool = True,
) -> dict[str, Any]:
    """运行所有样例，返回并写入一份 JSON 报告。"""

    case_data = json.loads(cases_path.read_text(encoding="utf-8"))
    if validate_cases:
        validate_eval_data(case_data)
    if dns_answers is None:
        dns_answers = case_data.get("dns_answers", {})
    original_getaddrinfo = None
    original_getaddrinfo = _install_controlled_dns_answers(dns_answers)

    started_at = perf_counter()
    try:
        results = [_evaluate_case(case) for case in case_data["cases"]]
    finally:
        if original_getaddrinfo is not None:
            _restore_dns_resolver(original_getaddrinfo)

    report = {
        "case_version": case_data["version"],
        "git_commit": _get_git_commit(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "rule_limitations": RULE_LIMITATIONS,
        "total_latency_ms": round((perf_counter() - started_at) * 1000, 3),
        "summary": _build_summary(results),
        "by_category": _build_category_summary(results),
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    started_at = perf_counter()
    runtime_exception = None
    try:
        actual = _check_case(case["input"])
    except Exception as error:  # 评测必须记录异常并继续执行其他样例。
        runtime_exception = type(error).__name__
        actual = {
            "decision": "error",
            "risk_type": None,
            "risk_level": None,
            "action": None,
            "reason_code": None,
            "masked_prompt": None,
        }
    latency_ms = round((perf_counter() - started_at) * 1000, 3)
    expected = {
        key: case.get(key)
        for key in (
            "expected_decision",
            "expected_risk_type",
            "expected_risk_level",
            "expected_action",
            "expected_reason_code",
            "expected_masked_prompt",
        )
        if key in case
    }
    passed = runtime_exception is None and _matches_expected(expected, actual)

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "tags": case.get("tags", []),
        "description": case["description"],
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "failure_type": (
            None
            if passed
            else _classify_failure(expected, actual, runtime_exception)
        ),
        "runtime_exception": runtime_exception,
        "latency_ms": latency_ms,
    }


def _check_case(case_input: dict[str, Any]) -> dict[str, Any]:
    check_input = SecurityCheckInput(
        prompt=case_input["prompt"],
        tool_name=case_input["tool_name"],
        target_url=case_input["target_url"],
        allowed_tools=tuple(case_input["allowed_tools"]),
    )
    for check in (check_prompt_injection, check_tool_allowlist, check_url_ssrf):
        result = check(check_input)
        if result.decision == "block":
            return {
                "decision": "block",
                "risk_type": result.risk_type,
                "risk_level": result.risk_level,
                "action": "blocked",
                "reason_code": result.reason_code,
                "masked_prompt": check_input.prompt,
            }

    pii_result = mask_pii(check_input)
    if pii_result.detected_types:
        return {
            "decision": "mask",
            "risk_type": "pii",
            "risk_level": "medium",
            "action": "masked",
            "reason_code": None,
            "masked_prompt": pii_result.masked_prompt,
        }
    return {
        "decision": "allow",
        "risk_type": None,
        "risk_level": "low",
        "action": None,
        "reason_code": None,
        "masked_prompt": pii_result.masked_prompt,
    }


def _matches_expected(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    field_mapping = {
        "expected_decision": "decision",
        "expected_risk_type": "risk_type",
        "expected_risk_level": "risk_level",
        "expected_action": "action",
        "expected_reason_code": "reason_code",
        "expected_masked_prompt": "masked_prompt",
    }
    return all(actual[field_mapping[key]] == value for key, value in expected.items())


def _classify_failure(
    expected: dict[str, Any],
    actual: dict[str, Any],
    runtime_exception: str | None,
) -> str:
    if runtime_exception is not None:
        return "runtime_exception"
    if expected["expected_decision"] == "allow" and actual["decision"] != "allow":
        return "false_positive"
    if (
        expected["expected_decision"] in {"block", "mask"}
        and actual["decision"] == "allow"
    ):
        return "false_negative"
    if expected["expected_risk_type"] != actual["risk_type"]:
        return "risk_type_error"
    if expected["expected_action"] != actual["action"]:
        return "action_error"
    if (
        "expected_masked_prompt" in expected
        and expected["expected_masked_prompt"] != actual["masked_prompt"]
    ):
        return "masking_error"
    if expected["expected_decision"] == "block" and actual["decision"] != "block":
        return "false_negative"
    if expected["expected_decision"] == "allow" and actual["decision"] != "allow":
        return "false_positive"
    return "incorrect_result"


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(results)
    passed_cases = sum(result["passed"] for result in results)
    failures = [result for result in results if not result["passed"]]
    latencies = sorted(result["latency_ms"] for result in results)
    p95_index = ceil(total_cases * 0.95) - 1 if total_cases else 0
    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": total_cases - passed_cases,
        "accuracy": round(passed_cases / total_cases, 4) if total_cases else 0,
        "false_positives": sum(
            result["failure_type"] == "false_positive" for result in failures
        ),
        "false_negatives": sum(
            result["failure_type"] == "false_negative" for result in failures
        ),
        "masking_errors": sum(
            result["failure_type"] == "masking_error" for result in failures
        ),
        "risk_type_errors": sum(
            result["failure_type"] == "risk_type_error" for result in failures
        ),
        "action_errors": sum(
            result["failure_type"] == "action_error" for result in failures
        ),
        "runtime_exceptions": sum(
            result["failure_type"] == "runtime_exception" for result in failures
        ),
        "average_latency_ms": round(
            sum(result["latency_ms"] for result in results) / total_cases, 3
        ) if total_cases else 0,
        "p95_latency_ms": latencies[p95_index] if total_cases else 0,
        "normal_case_ratio": round(
            sum("normal" in result["tags"] for result in results) / total_cases,
            4,
        ) if total_cases else 0,
    }


def _build_category_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, int | float]]:
    categories = sorted({result["category"] for result in results})
    return {
        category: _build_summary(
            [result for result in results if result["category"] == category]
        )
        for category in categories
    }


def _install_controlled_dns_answers(dns_answers: dict[str, list[str]]):
    import app.security_checks as security_checks

    original_getaddrinfo = security_checks.socket.getaddrinfo

    def controlled_getaddrinfo(host: str, *args: Any, **kwargs: Any):
        addresses = dns_answers.get(host.lower())
        if not addresses:
            raise security_checks.socket.gaierror("No configured DNS answer")
        return [(2, 1, 6, "", (address, 0)) for address in addresses]

    security_checks.socket.getaddrinfo = controlled_getaddrinfo
    return original_getaddrinfo


def _restore_dns_resolver(original_getaddrinfo: Any) -> None:
    import app.security_checks as security_checks

    security_checks.socket.getaddrinfo = original_getaddrinfo


def _get_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="离线运行安全评测")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    report = run_evaluation(cases_path=args.cases, report_path=args.report)
    summary = report["summary"]
    print(
        f"评测完成：{summary['passed_cases']}/{summary['total_cases']} 通过；"
        f"报告：{args.report}"
    )


if __name__ == "__main__":
    main()
