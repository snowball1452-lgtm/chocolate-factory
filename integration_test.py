#!/usr/bin/env python3
"""
Chocolate Factory Stack — Integration Test Suite
Tests the compiler, taste engine, and grants working together.
Run: cd docs/agent-control && python -m pytest integration_test.py -v
"""
import sys, os, random
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "compiler")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "adapters")))

from compiler.compiler import PolicyCompiler
from compiler.grants import Grant, GrantScope
from compiler.operators import compose_values, ABSENT
from taste_engine import Candidate, check_eligibility, compute_aggregate_score, select_action


def test_stage1_policy_compilation():
    """3-source composition: org > project > run restriction."""
    compiler = PolicyCompiler()
    sources = {
        "organization": "/models/allowed = [\"kimi-k2.6\", \"gpt-5.6-sol\", \"claude-fable-5\"]\n/authorization/network_allowed = true\n/run/maximum_cost = 200.0\n/organization/identity = \"chocolate-factory\"",
        "project": "/models/allowed = [\"kimi-k2.6\", \"gpt-5.6-sol\"]\n/run/maximum_cost = 150.0\n/project/display_name = \"Wonka Engine v2\"",
        "run": "/models/allowed = [\"kimi-k2.6\"]\n/run/maximum_cost = 80.0"
    }
    epd = compiler.compile(sources)
    assert epd.status == "SATISFIED"
    assert epd.values["/models/allowed"] == ["kimi-k2.6"]  # intersection: only kimi in all 3
    assert epd.values["/run/maximum_cost"] == 80.0  # min bound: lowest wins
    assert epd.values["/organization/identity"] == "chocolate-factory"
    assert epd.values["/project/display_name"] == "Wonka Engine v2"


def test_stage2_taste_engine_gates():
    """Harm gate blocks dangerous candidates regardless of expected value."""
    c_safe = Candidate("safe-boring", True, True, True, 0.05, 0.01,
        {"expected_value": 0.6, "novelty": 0.1, "exploration_bonus": 0.1, "playfulness": 0.2, "cost": 10.0})
    c_playful = Candidate("novel-playful", True, True, True, 0.15, 0.05,
        {"expected_value": 0.5, "novelty": 0.8, "exploration_bonus": 0.7, "playfulness": 0.9, "cost": 15.0})
    c_danger = Candidate("high-harm", True, True, True, 0.8, 0.3,
        {"expected_value": 0.95, "novelty": 0.5, "exploration_bonus": 0.3, "playfulness": 0.4, "cost": 5.0})
    all_cands = [c_safe, c_playful, c_danger]
    
    eligible = [c for c in all_cands if check_eligibility(c, 0.3, 0.1)]
    blocked = [c for c in all_cands if not check_eligibility(c, 0.3, 0.1)]
    assert len(eligible) == 2
    assert "high-harm" in [c.name for c in blocked]


def test_stage2b_taste_engine_ranking():
    """Playful candidate wins with novelty-weighted scoring."""
    c_safe = Candidate("safe-boring", True, True, True, 0.05, 0.01,
        {"expected_value": 0.6, "novelty": 0.1, "exploration_bonus": 0.1, "playfulness": 0.2, "cost": 10.0})
    c_playful = Candidate("novel-playful", True, True, True, 0.15, 0.05,
        {"expected_value": 0.5, "novelty": 0.8, "exploration_bonus": 0.7, "playfulness": 0.9, "cost": 15.0})
    all_cands = [c_safe, c_playful]
    weights = {"expected_value": 0.4, "novelty": 0.2, "exploration_bonus": 0.15, "playfulness": 0.15, "cost": 0.1}
    
    scores = [(c.name, compute_aggregate_score(c, weights, all_cands)) for c in all_cands]
    scores.sort(key=lambda x: x[1][0], reverse=True)
    assert scores[0][0] == "novel-playful"


def test_stage3_golden_ticket():
    """Grant expands a denied permission to SATISFIED."""
    compiler = PolicyCompiler()
    deny = compiler.compile({"organization": "/authorization/network_allowed = false"})
    assert deny.status == "DENIED"
    
    grant = Grant("gt-001", "organization", "sha256:org-id", "run", "sha256:default_run_identity",
        GrantScope(paths=["/authorization/network_allowed"], values={"/authorization/network_allowed": True}))
    epd = compiler.compile({"organization": "/authorization/network_allowed = false"}, grants=[grant])
    assert epd.status == "SATISFIED"
    assert epd.values["/authorization/network_allowed"] == True


def test_stage4_source_order_invariance():
    """Composition is order-independent."""
    compiler = PolicyCompiler()
    a = compiler.compile({"organization": '/models/allowed = ["a", "b"]', "project": '/models/allowed = ["a"]'})
    b = compiler.compile({"project": '/models/allowed = ["a"]', "organization": '/models/allowed = ["a", "b"]'})
    assert a.values == b.values


def test_stage5_lattice_properties():
    """Commutativity and idempotence for all operator types."""
    for op, x, y in [
        ("req_bool", True, False),
        ("perm_bool", True, False),
        ("allowlist", ["x", "y"], ["y", "z"]),
        ("max_bound", 10, 20),
        ("interval", [0, 10], [5, 15]),
    ]:
        assert compose_values(op, x, y) == compose_values(op, y, x), f"{op} not commutative"
        assert compose_values(op, x, x) == x, f"{op} not idempotent"


def test_stage6_exploration_policy():
    """Epsilon-greedy toggle between explore and exploit."""
    c_safe = Candidate("safe-boring", True, True, True, 0.05, 0.01,
        {"expected_value": 0.6, "novelty": 0.1, "exploration_bonus": 0.1, "playfulness": 0.2, "cost": 10.0})
    c_playful = Candidate("novel-playful", True, True, True, 0.15, 0.05,
        {"expected_value": 0.5, "novelty": 0.8, "exploration_bonus": 0.7, "playfulness": 0.9, "cost": 15.0})
    all_cands = [c_safe, c_playful]
    weights = {"expected_value": 0.4, "novelty": 0.2, "exploration_bonus": 0.15, "playfulness": 0.15, "cost": 0.1}
    
    random.seed(42)
    exploit_policy = {"type": "epsilon-greedy", "epsilon": 0.0, "floor": 0.0}
    pick, _ = select_action(all_cands, weights, exploit_policy, maximum_harm=0.3, maximum_catastrophic_risk=0.1)
    assert pick.name == "novel-playful"
