# docs/agent-control/adapters/test_adapters.py

import sys
import os
import json
import pytest
import urllib.error
from unittest.mock import patch, MagicMock

# Add compiler and adapters to sys.path to resolve direct imports without package prefixes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "compiler")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "adapters")))

# Import components directly
from taste_engine import (
    Candidate, check_eligibility, compose_weights, normalize_dimension,
    compute_aggregate_score, get_annealed_epsilon, select_action
)
from omniroute_adapter import OmniRouteAdapter
from meshos_adapter import MeshOSAdapter
from snowdrift_bridge import SnowDriftBridge
from factory_orchestrator import FactoryOrchestrator, PolicyCompiler


# ==========================================
# 1. Taste Engine Tests
# ==========================================

def test_taste_engine_eligibility_gates():
    """
    Test eligibility gates: ineligible candidates blocked regardless of upside.
    A candidate is eligible only if:
      integrity passes AND authorization passes AND required evidence exists AND
      harm upper confidence bound <= maximum harm AND catastrophic risk <= maximum catastrophic risk.
    """
    # Candidate with great expected value but integrity fails
    c1 = Candidate(
        name="Integrity Fail",
        integrity_passes=False,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.1,
        catastrophic_risk=0.05,
        dimensions={"expected_value": 0.99, "novelty": 0.5, "exploration_bonus": 0.5}
    )
    
    # Candidate with great expected value but auth fails
    c2 = Candidate(
        name="Auth Fail",
        integrity_passes=True,
        authorization_passes=False,
        required_evidence_exists=True,
        harm_upper_bound=0.1,
        catastrophic_risk=0.05,
        dimensions={"expected_value": 0.99}
    )

    # Candidate with great expected value but missing evidence
    c3 = Candidate(
        name="Evidence Fail",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=False,
        harm_upper_bound=0.1,
        catastrophic_risk=0.05,
        dimensions={"expected_value": 0.99}
    )

    # Candidate with too high harm
    c4 = Candidate(
        name="High Harm Fail",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.8,
        catastrophic_risk=0.05,
        dimensions={"expected_value": 0.99}
    )

    # Candidate with too high catastrophic risk
    c5 = Candidate(
        name="High Catastrophic Risk Fail",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.1,
        catastrophic_risk=0.8,
        dimensions={"expected_value": 0.99}
    )

    # Fully eligible candidate (moderate upside)
    c_eligible = Candidate(
        name="Perfect Eligible",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.2,
        catastrophic_risk=0.2,
        dimensions={"expected_value": 0.5}
    )

    # Test individual eligibility checks
    assert check_eligibility(c1, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is False
    assert check_eligibility(c2, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is False
    assert check_eligibility(c3, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is False
    assert check_eligibility(c4, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is False
    assert check_eligibility(c5, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is False
    assert check_eligibility(c_eligible, maximum_harm=0.5, maximum_catastrophic_risk=0.5) is True

    # Test selection: none of the ineligible ones should ever be chosen, only c_eligible
    candidates = [c1, c2, c3, c4, c5, c_eligible]
    weights = {"expected_value": 1.0}
    exploration_policy = {"strategy": "epsilon-greedy", "epsilon": 0.0} # exploit only
    
    selected, details = select_action(
        candidates=candidates,
        weights=weights,
        exploration_policy=exploration_policy,
        maximum_harm=0.5,
        maximum_catastrophic_risk=0.5
    )
    
    assert selected == c_eligible
    assert len(details) == 1
    assert details[0]["name"] == "Perfect Eligible"


def test_taste_engine_ranking_and_toggles():
    """
    Test correct aggregate score calculation and exploration strategy selection toggles.
    """
    c_exploit = Candidate(
        name="Exploit Candidate",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.1,
        catastrophic_risk=0.1,
        dimensions={"expected_value": 0.9, "novelty": 0.1, "exploration_bonus": 0.1}
    )
    
    c_explore = Candidate(
        name="Explore Candidate",
        integrity_passes=True,
        authorization_passes=True,
        required_evidence_exists=True,
        harm_upper_bound=0.1,
        catastrophic_risk=0.1,
        dimensions={"expected_value": 0.3, "novelty": 0.9, "exploration_bonus": 0.9}
    )

    candidates = [c_exploit, c_explore]
    
    # 1. Ranking weighted sum verification
    # weights: expected_value=0.8, novelty=0.2
    weights = {"expected_value": 0.8, "novelty": 0.2}
    
    # Score for c_exploit: 0.8 * 0.9 + 0.2 * 0.1 = 0.72 + 0.02 = 0.74
    # Score for c_explore: 0.8 * 0.3 + 0.2 * 0.9 = 0.24 + 0.18 = 0.42
    score_exploit, _ = compute_aggregate_score(c_exploit, weights, candidates)
    score_explore, _ = compute_aggregate_score(c_explore, weights, candidates)
    
    assert pytest.approx(score_exploit) == 0.74
    assert pytest.approx(score_explore) == 0.42

    # 2. Explore toggle - exploit only (epsilon-greedy, epsilon=0)
    selected, _ = select_action(
        candidates=candidates,
        weights=weights,
        exploration_policy={"strategy": "epsilon-greedy", "epsilon": 0.0},
        maximum_harm=0.5,
        maximum_catastrophic_risk=0.5
    )
    assert selected == c_exploit

    # 3. Explore toggle - explore only (epsilon-greedy, epsilon=1.0)
    # Since epsilon is 1, a random eligible candidate will be chosen. It can be c_exploit or c_explore.
    # Let's run multiple trials to verify we get both.
    selections = set()
    for _ in range(100):
        sel, _ = select_action(
            candidates=candidates,
            weights=weights,
            exploration_policy={"strategy": "epsilon-greedy", "epsilon": 1.0},
            maximum_harm=0.5,
            maximum_catastrophic_risk=0.5
        )
        selections.add(sel.name)
    assert "Exploit Candidate" in selections
    assert "Explore Candidate" in selections

    # 4. Explore toggle - UCB selection
    # ucb_score = aggregate_score + epsilon_t * exploration_bonus
    # If weights: expected_value=1.0, and ucb_multiplier=1.0 (epsilon=1.0)
    # c_exploit aggregate_score = 0.9. exploration_bonus = 0.1. UCB = 0.9 + 1.0 * 0.1 = 1.0
    # c_explore aggregate_score = 0.3. exploration_bonus = 0.9. UCB = 0.3 + 1.0 * 0.9 = 1.2
    # c_explore should be chosen!
    selected, _ = select_action(
        candidates=candidates,
        weights={"expected_value": 1.0},
        exploration_policy={"strategy": "ucb", "epsilon": 1.0, "annealing": "none"},
        maximum_harm=0.5,
        maximum_catastrophic_risk=0.5
    )
    assert selected == c_explore


def test_harm_gate_not_weight():
    """
    Harm MUST be a gate, not a weight.
    If harm_upper_bound weight > 0, compose_weights MUST emit a warning.
    """
    policies = [
        {"taste": {"weights": {"expected_value": 0.5, "harm_upper_bound": 0.1}}},
        {"taste": {"weights": {"novelty": 0.4}}}
    ]
    
    with pytest.warns(UserWarning, match="harm_upper_bound weight is greater than 0"):
        composed = compose_weights(policies)
        
    assert composed["harm_upper_bound"] == 0.1
    assert composed["expected_value"] == 0.5
    assert composed["novelty"] == 0.4


# ==========================================
# 2. OmniRoute Adapter Tests
# ==========================================

@patch("urllib.request.urlopen")
def test_omniroute_get_models(mock_urlopen):
    """
    Test OmniRoute list available models.
    """
    mock_res = MagicMock()
    mock_res.read.return_value = json.dumps({
        "data": [
            {"id": "kimi-k2.6"},
            {"id": "gpt-4"}
        ]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_res
    
    adapter = OmniRouteAdapter()
    models = adapter.get_available_models()
    assert models == ["kimi-k2.6", "gpt-4"]


@patch("urllib.request.urlopen")
def test_omniroute_route_request(mock_urlopen):
    """
    Test OmniRoute standard routing request.
    """
    mock_res = MagicMock()
    mock_res.read.return_value = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "Welcome to the chocolate factory!"}}]
    }).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_res
    
    adapter = OmniRouteAdapter()
    res = adapter.route_request("gpt-4", "Hello factory!")
    assert res["choices"][0]["message"]["content"] == "Welcome to the chocolate factory!"


@patch("urllib.request.urlopen")
def test_omniroute_fallback_chain(mock_urlopen):
    """
    Test fallback chain.
    If first model fails, it tries second, etc.
    """
    mock_fail = MagicMock()
    # Mock urlopen to raise an exception for the first call, and succeed on the second
    mock_success = MagicMock()
    mock_success.read.return_value = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "Succeeded on backup model!"}}]
    }).encode('utf-8')
    
    # We make a side_effect function
    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Model service unavailable")
        # Second call returns success response context manager
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_success
        return ctx
        
    mock_urlopen.side_effect = side_effect
    
    adapter = OmniRouteAdapter()
    res = adapter.fallback_chain(["gpt-4-faulty", "gpt-4-backup"], "Hello")
    assert res["choices"][0]["message"]["content"] == "Succeeded on backup model!"
    assert call_count == 2


# ==========================================
# 3. MeshOS Adapter Tests
# ==========================================

@patch("urllib.request.urlopen")
def test_meshos_store_retrieve_epd(mock_urlopen):
    """
    Test EPD storage and retrieval.
    """
    # 1. Test Store EPD
    mock_store_res = MagicMock()
    mock_store_res.read.return_value = json.dumps({
        "data": {
            "insert_epd_one": {
                "id": "epd-uuid-1234"
            }
        }
    }).encode('utf-8')
    
    mock_retrieve_res = MagicMock()
    mock_retrieve_res.read.return_value = json.dumps({
        "data": {
            "epd_by_pk": {
                "id": "epd-uuid-1234",
                "epd": {"/integrity/sandbox_required": True},
                "agent_id": "agent-007"
            }
        }
    }).encode('utf-8')
    
    # Set up urlopen side_effect for store then retrieve
    call_ctx = []
    def side_effect(*args, **kwargs):
        ctx = MagicMock()
        if not call_ctx:
            ctx.__enter__.return_value = mock_store_res
            call_ctx.append(True)
        else:
            ctx.__enter__.return_value = mock_retrieve_res
        return ctx
        
    mock_urlopen.side_effect = side_effect
    
    adapter = MeshOSAdapter()
    epd_id = adapter.store_epd({"/integrity/sandbox_required": True}, "agent-007")
    assert epd_id == "epd-uuid-1234"
    
    retrieved = adapter.retrieve_epd("epd-uuid-1234")
    assert retrieved["agent_id"] == "agent-007"
    assert retrieved["epd"]["/integrity/sandbox_required"] is True


@patch("urllib.request.urlopen")
def test_meshos_store_recall_link_memories(mock_urlopen):
    """
    Test storing memory, recalling memory, and linking memories.
    """
    mock_store = MagicMock()
    mock_store.read.return_value = json.dumps({
        "data": {
            "insert_memory_one": {"id": "mem-1"}
        }
    }).encode('utf-8')
    
    mock_recall = MagicMock()
    mock_recall.read.return_value = json.dumps({
        "data": {
            "memory": [
                {"id": "mem-1", "content": "Database audit succeeded", "memory_type": "audit"}
            ]
        }
    }).encode('utf-8')

    mock_link = MagicMock()
    mock_link.read.return_value = json.dumps({
        "data": {
            "insert_memory_edge_one": {"id": "edge-100"}
        }
    }).encode('utf-8')

    mock_history = MagicMock()
    mock_history.read.return_value = json.dumps({
        "data": {
            "memory": [
                {"id": "mem-1", "content": "Database audit succeeded", "memory_type": "audit"}
            ]
        }
    }).encode('utf-8')

    calls = 0
    def side_effect(*args, **kwargs):
        nonlocal calls
        calls += 1
        ctx = MagicMock()
        if calls == 1:
            ctx.__enter__.return_value = mock_store
        elif calls == 2:
            ctx.__enter__.return_value = mock_recall
        elif calls == 3:
            ctx.__enter__.return_value = mock_link
        else:
            ctx.__enter__.return_value = mock_history
        return ctx

    mock_urlopen.side_effect = side_effect
    
    adapter = MeshOSAdapter()
    
    # Store memory
    mem_id = adapter.store_memory("Database audit succeeded", "agent-007", "audit")
    assert mem_id == "mem-1"
    
    # Recall memory
    recalled = adapter.recall("audit", "agent-007")
    assert len(recalled) == 1
    assert recalled[0]["id"] == "mem-1"
    
    # Link memory
    edge_id = adapter.link_memories("mem-1", "mem-2", "supports")
    assert edge_id == "edge-100"
    
    # Agent History
    history = adapter.get_agent_history("agent-007")
    assert len(history) == 1
    assert history[0]["content"] == "Database audit succeeded"


# ==========================================
# 4. SnowDrift Bridge Tests
# ==========================================

@patch("urllib.request.urlopen")
def test_snowdrift_bridge_operations(mock_urlopen):
    """
    Test mobile SnowDrift bridge operations: sync, push, status, task delegation.
    """
    mock_sync = MagicMock()
    mock_sync.read.return_value = json.dumps({"status": "synchronized"}).encode('utf-8')
    
    mock_push = MagicMock()
    mock_push.read.return_value = json.dumps({"status": "policy_applied"}).encode('utf-8')
    
    mock_status = MagicMock()
    mock_status.read.return_value = json.dumps({"device_id": "pixel_9", "battery": 87}).encode('utf-8')
    
    mock_task = MagicMock()
    mock_task.read.return_value = json.dumps({"task_id": "t-50", "status": "processing"}).encode('utf-8')
    
    mock_result = MagicMock()
    mock_result.read.return_value = json.dumps({"status": "completed", "result": "location fetched"}).encode('utf-8')
    
    calls = 0
    def side_effect(*args, **kwargs):
        nonlocal calls
        calls += 1
        ctx = MagicMock()
        if calls == 1:
            ctx.__enter__.return_value = mock_sync
        elif calls == 2:
            ctx.__enter__.return_value = mock_push
        elif calls == 3:
            ctx.__enter__.return_value = mock_status
        elif calls == 4:
            ctx.__enter__.return_value = mock_task
        else:
            ctx.__enter__.return_value = mock_result
        return ctx
        
    mock_urlopen.side_effect = side_effect
    
    bridge = SnowDriftBridge()
    
    # Sync memory
    res_sync = bridge.sync_memory("agent-007")
    assert res_sync["status"] == "synchronized"
    
    # Push EPD
    res_push = bridge.push_policy_epd("agent-007", {"/integrity/sandbox_required": True})
    assert res_push["status"] == "policy_applied"
    
    # Get Status
    res_status = bridge.get_mobile_status("pixel_9")
    assert res_status["battery"] == 87
    
    # Send Task
    res_task = bridge.send_task_to_mobile("agent-007", {"action": "get_gps"})
    assert res_task["task_id"] == "t-50"
    
    # Get Result
    res_res = bridge.receive_mobile_result("t-50")
    assert res_res["result"] == "location fetched"


# ==========================================
# 5. Factory Orchestrator Full Loop Test
# ==========================================

@patch("urllib.request.urlopen")
def test_factory_orchestrator_full_loop(mock_urlopen):
    """
    Test orchestrator initialization, compiling policy, routing, recalling and full loop step.
    We mock the external GraphQL/FastAPI calls to test clean integration.
    """
    # 1. EPD storage mock
    mock_store_epd = MagicMock()
    mock_store_epd.read.return_value = json.dumps({"data": {"insert_epd_one": {"id": "epd-1"}}}).encode('utf-8')
    
    # 2. Push policy mock
    mock_push_policy = MagicMock()
    mock_push_policy.read.return_value = json.dumps({"status": "applied"}).encode('utf-8')
    
    # 3. Store decision memory mock
    mock_store_mem = MagicMock()
    mock_store_mem.read.return_value = json.dumps({"data": {"insert_memory_one": {"id": "mem-react"}}}).encode('utf-8')
    
    # 4. Sync memory mock
    mock_sync_mem = MagicMock()
    mock_sync_mem.read.return_value = json.dumps({"status": "success"}).encode('utf-8')
    
    calls = 0
    def side_effect(*args, **kwargs):
        nonlocal calls
        calls += 1
        ctx = MagicMock()
        if calls == 1:
            ctx.__enter__.return_value = mock_store_epd
        elif calls == 2:
            ctx.__enter__.return_value = mock_push_policy
        elif calls == 3:
            ctx.__enter__.return_value = mock_store_mem
        else:
            ctx.__enter__.return_value = mock_sync_mem
        return ctx
        
    mock_urlopen.side_effect = side_effect
    
    orchestrator = FactoryOrchestrator()
    
    # Step A: Compile policy sources
    sources = [
        {
            "source": "organization",
            "values": {
                "/integrity/sandbox_required": True,
                "/taste/weights/expected_value": 0.8,
                "/taste/weights/novelty": 0.2,
                "/taste/exploration/strategy": "epsilon-greedy",
                "/taste/exploration/epsilon": 0.0, # strictly exploit
            }
        }
    ]
    
    epd = orchestrator.compile_policy(sources, "agent-007")
    assert epd["/integrity/sandbox_required"] is True
    assert epd["/taste/weights/expected_value"] == 0.8
    assert epd["/taste/weights/novelty"] == 0.2
    assert epd["/taste/exploration/strategy"] == "epsilon-greedy"
    assert epd["/taste/exploration/epsilon"] == 0.0

    # Step B: Run Loop step decision
    candidates = [
        Candidate(
            name="Explore task",
            integrity_passes=True,
            authorization_passes=True,
            required_evidence_exists=True,
            harm_upper_bound=0.1,
            catastrophic_risk=0.1,
            dimensions={"expected_value": 0.2, "novelty": 0.9}
        ),
        Candidate(
            name="Exploit task",
            integrity_passes=True,
            authorization_passes=True,
            required_evidence_exists=True,
            harm_upper_bound=0.1,
            catastrophic_risk=0.1,
            dimensions={"expected_value": 0.9, "novelty": 0.2}
        )
    ]
    
    selected, details = orchestrator.execute_loop_iteration(
        agent_id="agent-007",
        candidates=candidates,
        prompt="Process next task",
        step=1
    )
    
    assert selected is not None
    assert selected.name == "Exploit task"
    assert details["step"] == 1
    assert details["decision_memory_id"] == "mem-react"
