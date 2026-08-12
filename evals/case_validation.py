"""安全评测样例的共享校验规则。"""

from typing import Any


_REQUIRED_CASE_FIELDS = {"case_id", "category", "input", "expected_decision", "expected_risk_type", "expected_risk_level", "expected_action", "expected_reason_code", "description", "tags"}
_INPUT_FIELDS = {"prompt", "tool_name", "target_url", "allowed_tools"}
_CATEGORIES = {"benign", "prompt_injection", "pii", "tool", "ssrf"}
_DECISIONS = {"allow", "block", "mask"}
_RISK_LEVELS = {"low", "medium", "high"}
_ACTIONS = {None, "blocked", "masked"}
_TAGS = {"normal", "attack", "sensitive", "boundary", "bypass"}
_REQUIRED_DNS_NAMES = {"public.example", "private.example", "mixed.example", "missing.example"}


def validate_eval_data(eval_data: dict[str, Any], minimum_cases: int = 30) -> None:
    """验证评测文件，错误时抛出可读的 ValueError。"""
    cases = eval_data.get("cases")
    if not isinstance(cases, list) or len(cases) < minimum_cases:
        raise ValueError(f"评测样例至少需要 {minimum_cases} 条")
    case_ids = []
    for case in cases:
        _validate_case(case)
        case_ids.append(case["case_id"])
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("case_id 必须唯一")
    _validate_category_coverage(cases)
    _validate_dns_answers(eval_data.get("dns_answers"))


def _validate_case(case: Any) -> None:
    if not isinstance(case, dict) or not _REQUIRED_CASE_FIELDS <= case.keys():
        raise ValueError("每条样例必须包含规定字段")
    if not isinstance(case["case_id"], str) or not case["case_id"]:
        raise ValueError("case_id 必须是非空字符串")
    if case["category"] not in _CATEGORIES:
        raise ValueError("category 不在允许范围")
    if not isinstance(case["input"], dict) or set(case["input"]) != _INPUT_FIELDS:
        raise ValueError("input 必须包含 prompt、tool_name、target_url、allowed_tools")
    case_input = case["input"]
    if not isinstance(case_input["prompt"], str):
        raise ValueError("input.prompt 必须是字符串")
    if case_input["tool_name"] is not None and not isinstance(case_input["tool_name"], str):
        raise ValueError("input.tool_name 必须是字符串或 null")
    if case_input["target_url"] is not None and not isinstance(case_input["target_url"], str):
        raise ValueError("input.target_url 必须是字符串或 null")
    if not isinstance(case_input["allowed_tools"], list) or not all(isinstance(tool, str) for tool in case_input["allowed_tools"]):
        raise ValueError("input.allowed_tools 必须是字符串列表")
    if case["expected_decision"] not in _DECISIONS:
        raise ValueError("expected_decision 不在允许范围")
    if case["expected_risk_level"] not in _RISK_LEVELS:
        raise ValueError("expected_risk_level 不在允许范围")
    if case["expected_action"] not in _ACTIONS:
        raise ValueError("expected_action 不在允许范围")
    if case["expected_risk_type"] is not None and not isinstance(case["expected_risk_type"], str):
        raise ValueError("expected_risk_type 必须是字符串或 null")
    if case["expected_reason_code"] is not None and not isinstance(case["expected_reason_code"], str):
        raise ValueError("expected_reason_code 必须是字符串或 null")
    if not isinstance(case["description"], str) or not case["description"]:
        raise ValueError("description 必须是非空字符串")
    if not isinstance(case["tags"], list) or not case["tags"] or not set(case["tags"]) <= _TAGS:
        raise ValueError("tags 不在允许范围")
    if case["expected_decision"] == "allow":
        if case["expected_action"] is not None or case["expected_risk_type"] is not None:
            raise ValueError("allow 样例不能设置安全动作或风险类型")
    elif case["expected_decision"] == "block":
        if case["expected_action"] != "blocked" or case["expected_risk_type"] is None:
            raise ValueError("block 样例必须设置 blocked 动作和风险类型")
    elif case["expected_action"] != "masked" or case["expected_risk_type"] != "pii" or not isinstance(case.get("expected_masked_prompt"), str):
        raise ValueError("mask 样例必须设置 pii、masked 和 expected_masked_prompt")


def _validate_category_coverage(cases: list[dict[str, Any]]) -> None:
    if sum("normal" in case["tags"] for case in cases) / len(cases) < 0.3:
        raise ValueError("normal 标签样例比例必须不少于 30%")
    required_tags = {"prompt_injection": {"normal", "attack", "boundary"}, "tool": {"normal", "attack", "boundary"}, "ssrf": {"normal", "attack", "boundary"}, "pii": {"normal", "sensitive", "boundary"}}
    for category, expected_tags in required_tags.items():
        category_tags = {tag for case in cases if case["category"] == category for tag in case["tags"]}
        if not expected_tags <= category_tags:
            raise ValueError(f"{category} 缺少所需标签")


def _validate_dns_answers(dns_answers: Any) -> None:
    if not isinstance(dns_answers, dict) or not _REQUIRED_DNS_NAMES <= dns_answers.keys():
        raise ValueError("dns_answers 缺少固定域名映射")
    if not all(isinstance(hostname, str) and isinstance(addresses, list) and all(isinstance(address, str) for address in addresses) for hostname, addresses in dns_answers.items()):
        raise ValueError("dns_answers 必须是域名到 IP 字符串列表的映射")
