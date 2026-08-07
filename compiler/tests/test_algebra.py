# docs/agent-control/compiler/tests/test_algebra.py

import pytest
from ..operators import compose_values, is_less_permissive_or_equal, ABSENT

# Define sample test values for each operator type
TEST_CASES = {
    "req_bool": [True, False, ABSENT],
    "forbidden_bool": [True, False, ABSENT],
    "perm_bool": [True, False, ABSENT],
    "allowlist": [["a", "b"], ["b"], [], ABSENT],
    "denylist": [["a", "b"], ["b"], [], ABSENT],
    "max_bound": [10, 20, ABSENT],
    "min_bound": [5, 15, ABSENT],
    "interval": [[1, 10], [5, 15], [8, 7], ABSENT],  # [8, 7] is unsatisfiable (bottom)
    "obligation_set": [["check1", "check2"], ["check2"], [], ABSENT],
    "ordered_floor": ["public", "internal", "confidential", "restricted", ABSENT],
    "predicate_rules": [
        [{"metric": "request.error_rate", "operator": "gt", "threshold": 0.05, "unit": "one", "window_seconds": 300, "aggregation": "rate", "minimum_samples": 100}],
        [{"metric": "system.cpu_usage", "operator": "gt", "threshold": 0.8, "unit": "percent", "window_seconds": 60, "aggregation": "avg", "minimum_samples": 10}],
        [],
        ABSENT
    ]
}

@pytest.mark.parametrize("op_type", TEST_CASES.keys())
def test_commutativity(op_type):
    vals = TEST_CASES[op_type]
    for a in vals:
        for b in vals:
            res_ab = compose_values(op_type, a, b)
            res_ba = compose_values(op_type, b, a)
            assert res_ab == res_ba

@pytest.mark.parametrize("op_type", TEST_CASES.keys())
def test_associativity(op_type):
    vals = TEST_CASES[op_type]
    for a in vals:
        for b in vals:
            for c in vals:
                res_1 = compose_values(op_type, compose_values(op_type, a, b), c)
                res_2 = compose_values(op_type, a, compose_values(op_type, b, c))
                assert res_1 == res_2

@pytest.mark.parametrize("op_type", TEST_CASES.keys())
def test_idempotence(op_type):
    vals = TEST_CASES[op_type]
    for a in vals:
        res = compose_values(op_type, a, a)
        assert res == a

@pytest.mark.parametrize("op_type", TEST_CASES.keys())
def test_restriction(op_type):
    """
    Test restriction: compose(A, B) ⪯ A and compose(A, B) ⪯ B.
    A ⪯ B iff A is no more permissive than B.
    """
    vals = TEST_CASES[op_type]
    for a in vals:
        for b in vals:
            res = compose_values(op_type, a, b)
            # res ⪯ a
            assert is_less_permissive_or_equal(op_type, res, a), f"Failed: compose({a}, {b})={res} ⪯ {a} for {op_type}"
            # res ⪯ b
            assert is_less_permissive_or_equal(op_type, res, b), f"Failed: compose({a}, {b})={res} ⪯ {b} for {op_type}"
