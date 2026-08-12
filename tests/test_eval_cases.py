import json
from pathlib import Path


EVAL_CASES_PATH = Path(__file__).parent.parent / "evals" / "security_cases.json"
REQUIRED_FIELDS = {
    "case_id",
    "category",
    "input",
    "expected_decision",
    "expected_risk_type",
    "expected_risk_level",
    "expected_action",
    "expected_reason_code",
    "description",
    "tags",
}


def test_first_security_eval_cases_have_a_consistent_structure():
    """首批评测样例是数据，不计入安全规则的测试数量。"""

    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]

    assert len(cases) >= 50
    assert len({case["case_id"] for case in cases}) == len(cases)

    for case in cases:
        assert REQUIRED_FIELDS <= case.keys()
        assert set(case["input"]) == {
            "prompt",
            "tool_name",
            "target_url",
            "allowed_tools",
        }
        assert case["category"] in {
            "benign", "prompt_injection", "pii", "tool", "ssrf"
        }
        assert isinstance(case["input"]["prompt"], str)
        assert case["input"]["tool_name"] is None or isinstance(case["input"]["tool_name"], str)
        assert case["input"]["target_url"] is None or isinstance(case["input"]["target_url"], str)
        assert all(isinstance(tool, str) for tool in case["input"]["allowed_tools"])
        assert case["expected_decision"] in {"allow", "block", "mask"}
        assert case["expected_risk_level"] in {"low", "medium", "high"}
        assert case["expected_action"] in {None, "blocked", "masked"}
        assert case["description"]
        assert set(case["tags"]) <= {
            "normal", "attack", "sensitive", "boundary", "bypass"
        }
        assert case["tags"]
        if case["expected_decision"] == "allow":
            assert case["expected_action"] is None
            assert case["expected_risk_type"] is None
        elif case["expected_decision"] == "block":
            assert case["expected_action"] == "blocked"
            assert case["expected_risk_type"] is not None
        else:
            assert case["expected_action"] == "masked"
            assert case["expected_risk_type"] == "pii"
            assert "expected_masked_prompt" in case


def test_pii_eval_cases_include_the_expected_masked_prompt():
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    pii_cases = [case for case in cases if case["category"] == "pii"]

    assert all("expected_masked_prompt" in case for case in pii_cases)
    assert all(case["expected_decision"] in {"allow", "mask"} for case in pii_cases)


def test_each_risk_category_has_normal_attack_and_boundary_cases():
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]

    for category in ("prompt_injection", "tool", "ssrf"):
        category_tags = {
            tag for case in cases if case["category"] == category for tag in case["tags"]
        }
        assert {"normal", "attack", "boundary"} <= category_tags

    pii_tags = {
        tag for case in cases if case["category"] == "pii" for tag in case["tags"]
    }
    assert {"normal", "sensitive", "boundary"} <= pii_tags


def test_normal_cases_are_at_least_thirty_percent_of_the_eval_set():
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]

    normal_cases = [case for case in cases if "normal" in case["tags"]]

    assert len(normal_cases) / len(cases) >= 0.3


def test_fifty_case_eval_set_has_balanced_category_coverage():
    cases = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    category_counts = {
        category: sum(case["category"] == category for case in cases)
        for category in ("prompt_injection", "pii", "tool", "ssrf")
    }

    assert 10 <= category_counts["prompt_injection"] <= 15
    assert 10 <= category_counts["pii"] <= 15
    assert 8 <= category_counts["tool"] <= 10
    assert 10 <= category_counts["ssrf"] <= 15


def test_eval_cases_define_fixed_dns_answers_for_offline_ssrf_evaluation():
    eval_data = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))

    assert set(eval_data["dns_answers"]) >= {
        "public.example", "private.example", "mixed.example", "missing.example"
    }
    assert eval_data["dns_answers"]["public.example"] == ["8.8.8.8"]
    assert eval_data["dns_answers"]["private.example"] == ["10.0.0.1"]
    assert eval_data["dns_answers"]["mixed.example"] == ["8.8.8.8", "10.0.0.1"]
    assert eval_data["dns_answers"]["missing.example"] == []
