import copy
import json
from pathlib import Path

import pytest

from evals.case_validation import validate_eval_data


EVAL_CASES_PATH = Path(__file__).parent.parent / "evals" / "security_cases.json"


def test_validate_eval_data_accepts_the_current_fifty_case_dataset():
    eval_data = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))

    validate_eval_data(eval_data)


def test_validate_eval_data_rejects_an_invalid_case_action():
    eval_data = json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))
    invalid_data = copy.deepcopy(eval_data)
    invalid_data["cases"][0]["expected_action"] = "allowed"

    with pytest.raises(ValueError, match="expected_action"):
        validate_eval_data(invalid_data)
