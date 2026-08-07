# docs/agent-control/compiler/tests/test_operators.py

import pytest
from ..operators import compose_values, ABSENT

def test_req_bool():
    # present values
    assert compose_values("req_bool", True, False) is True
    assert compose_values("req_bool", True, True) is True
    assert compose_values("req_bool", False, False) is False
    # absent values
    assert compose_values("req_bool", True, ABSENT) is True
    assert compose_values("req_bool", ABSENT, False) is False
    assert compose_values("req_bool", ABSENT, ABSENT) is ABSENT

def test_forbidden_bool():
    assert compose_values("forbidden_bool", True, False) is True
    assert compose_values("forbidden_bool", True, ABSENT) is True
    assert compose_values("forbidden_bool", ABSENT, ABSENT) is ABSENT

def test_perm_bool():
    # present values
    assert compose_values("perm_bool", True, False) is False
    assert compose_values("perm_bool", True, True) is True
    # absent values
    assert compose_values("perm_bool", True, ABSENT) is True
    assert compose_values("perm_bool", ABSENT, False) is False
    assert compose_values("perm_bool", ABSENT, ABSENT) is ABSENT

def test_allowlist():
    # present values
    assert compose_values("allowlist", ["a", "b"], ["b", "c"]) == ["b"]
    # absent values
    assert compose_values("allowlist", ["a", "b"], ABSENT) == ["a", "b"]
    # explicit empty
    assert compose_values("allowlist", ["a", "b"], []) == []
    assert compose_values("allowlist", [], ABSENT) == []
    assert compose_values("allowlist", ABSENT, ABSENT) is ABSENT

def test_denylist():
    assert compose_values("denylist", ["a"], ["b"]) == ["a", "b"]
    assert compose_values("denylist", ["a"], ABSENT) == ["a"]
    assert compose_values("denylist", ["a"], []) == ["a"]
    assert compose_values("denylist", ABSENT, ABSENT) is ABSENT

def test_max_bound():
    assert compose_values("max_bound", 100, 200) == 100
    assert compose_values("max_bound", 100, ABSENT) == 100
    assert compose_values("max_bound", ABSENT, ABSENT) is ABSENT

def test_min_bound():
    assert compose_values("min_bound", 10, 20) == 20
    assert compose_values("min_bound", 10, ABSENT) == 10
    assert compose_values("min_bound", ABSENT, ABSENT) is ABSENT

def test_interval():
    assert compose_values("interval", [1, 10], [5, 15]) == [5, 10]
    assert compose_values("interval", [1, 10], ABSENT) == [1, 10]
    # unsatisfiable
    assert compose_values("interval", [1, 5], [10, 15]) == [10, 5]
    assert compose_values("interval", ABSENT, ABSENT) is ABSENT

def test_obligation_set():
    assert compose_values("obligation_set", ["a"], ["b"]) == ["a", "b"]
    assert compose_values("obligation_set", ["a"], ABSENT) == ["a"]
    assert compose_values("obligation_set", ["a"], []) == ["a"]
    assert compose_values("obligation_set", ABSENT, ABSENT) is ABSENT

def test_ordered_floor():
    assert compose_values("ordered_floor", "internal", "restricted") == "restricted"
    assert compose_values("ordered_floor", "internal", ABSENT) == "internal"
    assert compose_values("ordered_floor", ABSENT, ABSENT) is ABSENT

def test_predicate_rules():
    r1 = {"metric": "request.error_rate", "operator": "gt", "threshold": 0.05}
    r2 = {"metric": "system.cpu_usage", "operator": "gt", "threshold": 0.8}
    assert compose_values("predicate_rules", [r1], [r2]) == [r1, r2] if r1["metric"] < r2["metric"] else [r2, r1]
    assert compose_values("predicate_rules", [r1], ABSENT) == [r1]
    # Deduplication
    assert compose_values("predicate_rules", [r1], [r1]) == [r1]
