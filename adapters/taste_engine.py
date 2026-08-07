# docs/agent-control/adapters/taste_engine.py

import random
import math
import warnings
from typing import List, Dict, Any, Union, Tuple, Optional

class Candidate:
    """
    Represents an action candidate in the ReAct loop.
    """
    def __init__(
        self,
        name: str,
        integrity_passes: bool,
        authorization_passes: bool,
        required_evidence_exists: bool,
        harm_upper_bound: float,
        catastrophic_risk: float,
        dimensions: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.integrity_passes = integrity_passes
        self.authorization_passes = authorization_passes
        self.required_evidence_exists = required_evidence_exists
        self.harm_upper_bound = harm_upper_bound
        self.catastrophic_risk = catastrophic_risk
        self.dimensions = dimensions or {}
        
        # Ensure standard dimensions exist
        if "expected_value" not in self.dimensions:
            self.dimensions["expected_value"] = 0.0
        if "novelty" not in self.dimensions:
            self.dimensions["novelty"] = 0.0
        if "exploration_bonus" not in self.dimensions:
            self.dimensions["exploration_bonus"] = 0.0
        if "playfulness" not in self.dimensions:
            self.dimensions["playfulness"] = 0.0
        if "cost" not in self.dimensions:
            self.dimensions["cost"] = 0.0
        if "harm_upper_bound" not in self.dimensions:
            self.dimensions["harm_upper_bound"] = harm_upper_bound
            
        self.metadata = metadata or {}

    def __repr__(self):
        return f"Candidate({self.name})"


def check_eligibility(
    candidate: Union[Candidate, Dict[str, Any]],
    maximum_harm: float,
    maximum_catastrophic_risk: float
) -> bool:
    """
    Eligibility gate checks.
    A candidate is eligible only if:
      integrity passes
      AND authorization passes
      AND required evidence exists
      AND harm upper confidence bound <= maximum harm
      AND catastrophic risk <= maximum catastrophic risk
    """
    if isinstance(candidate, Candidate):
        integrity = candidate.integrity_passes
        auth = candidate.authorization_passes
        evidence = candidate.required_evidence_exists
        harm = candidate.harm_upper_bound
        cat_risk = candidate.catastrophic_risk
    else:
        integrity = candidate.get("integrity_passes", False)
        auth = candidate.get("authorization_passes", False)
        evidence = candidate.get("required_evidence_exists", False)
        harm = candidate.get("harm_upper_bound", 1.0)
        cat_risk = candidate.get("catastrophic_risk", 1.0)

    return (
        bool(integrity) and
        bool(auth) and
        bool(evidence) and
        harm <= maximum_harm and
        cat_risk <= maximum_catastrophic_risk
    )


def compose_weights(policies: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Dimension weights compose as ordered floor (highest required weight wins) across policy sources.
    If harm_upper_bound has a non-zero weight, emit a warning.
    """
    composed = {
        "expected_value": 0.0,
        "novelty": 0.0,
        "exploration_bonus": 0.0,
        "playfulness": 0.0,
        "cost": 0.0,
        "harm_upper_bound": 0.0
    }
    
    for policy in policies:
        # Check if weights is nested under taste.weights or just weights
        weights = policy.get("taste", {}).get("weights", {}) if "taste" in policy else policy.get("weights", {})
        for k in composed:
            if k in weights:
                composed[k] = max(composed[k], float(weights[k]))
                
    if composed.get("harm_upper_bound", 0.0) > 0.0:
        warnings.warn(
            "harm_upper_bound weight is greater than 0. harm SHOULD be a gate, not a ranking signal.",
            UserWarning,
            stacklevel=2
        )
        
    return composed


def normalize_dimension(
    val: float,
    dimension_name: str,
    all_candidates: List[Union[Candidate, Dict[str, Any]]]
) -> float:
    """
    Normalize dimension values to [0, 1].
    expected_value, novelty, exploration_bonus, playfulness: raw values since they are already [0, 1].
    harm_upper_bound: 1.0 - harm (lower is better)
    cost: lower is better, relative min-max or 1/(1+cost)
    """
    if dimension_name in ["expected_value", "novelty", "exploration_bonus", "playfulness"]:
        return max(0.0, min(1.0, val))
    elif dimension_name == "harm_upper_bound":
        return max(0.0, min(1.0, 1.0 - val))
    elif dimension_name == "cost":
        costs = []
        for c in all_candidates:
            c_dims = getattr(c, "dimensions", {}) if isinstance(c, Candidate) else c.get("dimensions", {})
            costs.append(c_dims.get("cost", 0.0))
        if not costs:
            return 1.0 / (1.0 + val)
        min_cost = min(costs)
        max_cost = max(costs)
        if max_cost > min_cost:
            return (max_cost - val) / (max_cost - min_cost)
        else:
            return 1.0 / (1.0 + val) if val > 0 else 1.0
    return val


def compute_aggregate_score(
    candidate: Union[Candidate, Dict[str, Any]],
    weights: Dict[str, float],
    all_candidates: List[Union[Candidate, Dict[str, Any]]]
) -> Tuple[float, Dict[str, float]]:
    """
    Aggregate score is a weighted sum of normalized dimension values:
      score = Σ(weight_i × normalize(dimension_i))
    """
    dims = getattr(candidate, "dimensions", {}) if isinstance(candidate, Candidate) else candidate.get("dimensions", {})
    normalized = {}
    for dim_name in weights:
        val = dims.get(dim_name, 0.0)
        normalized[dim_name] = normalize_dimension(val, dim_name, all_candidates)
        
    score = sum(weights.get(k, 0.0) * normalized[k] for k in normalized)
    return score, normalized


def get_annealed_epsilon(
    epsilon: float,
    annealing_type: str,
    floor: float,
    step: int,
    decay_rate: Optional[float] = None
) -> float:
    """
    Applies annealing to epsilon/exploration parameter over steps.
    """
    if step <= 0:
        return epsilon
    if annealing_type == "linear":
        decay = decay_rate if decay_rate is not None else 0.01
        return max(floor, epsilon - decay * step)
    elif annealing_type == "exponential":
        decay = decay_rate if decay_rate is not None else 0.1
        return max(floor, epsilon * math.exp(-decay * step))
    return epsilon


def select_action(
    candidates: List[Union[Candidate, Dict[str, Any]]],
    weights: Dict[str, float],
    exploration_policy: Dict[str, Any],
    step: int = 0,
    maximum_harm: float = 0.5,
    maximum_catastrophic_risk: float = 0.5,
    decay_rate: Optional[float] = None
) -> Tuple[Optional[Union[Candidate, Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    Taste Engine decision function inside the ReAct loop:
    1. Filter out candidates by eligibility gates (safety gates fire first).
    2. Rank remaining candidates using aggregate score.
    3. Apply exploration policy (epsilon-greedy, thompson-sampling, or ucb).
    
    Returns:
      (selected_candidate, candidate_scores_list)
    """
    # 1. Eligibility gate check
    eligible_candidates = [
        c for c in candidates if check_eligibility(c, maximum_harm, maximum_catastrophic_risk)
    ]
    
    if not eligible_candidates:
        return None, []
        
    # 2. Score candidates
    scored_candidates = []
    for c in eligible_candidates:
        score, normalized_dims = compute_aggregate_score(c, weights, eligible_candidates)
        scored_candidates.append({
            "candidate": c,
            "score": score,
            "normalized": normalized_dims
        })
        
    # 3. Apply exploration policy
    strategy = exploration_policy.get("strategy", "epsilon-greedy")
    epsilon = exploration_policy.get("epsilon", 0.15)
    annealing = exploration_policy.get("annealing", "none")
    floor = exploration_policy.get("floor", 0.05)
    
    epsilon_t = get_annealed_epsilon(epsilon, annealing, floor, step, decay_rate)
    
    selected_record = None
    
    if strategy == "epsilon-greedy":
        # Sort by score descending to find the best exploitation candidate
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        if random.random() < epsilon_t:
            # Explore: pick random from all eligible candidates
            selected_record = random.choice(scored_candidates)
        else:
            # Exploit: pick highest score
            selected_record = scored_candidates[0]
            
    elif strategy == "thompson-sampling":
        # For Thompson-sampling, sample for each candidate
        # We can treat expected_value as the mean and exploration_bonus (or a default) as standard deviation
        sampled_candidates = []
        for item in scored_candidates:
            c = item["candidate"]
            dims = getattr(c, "dimensions", {}) if isinstance(c, Candidate) else c.get("dimensions", {})
            ev = dims.get("expected_value", 0.5)
            eb = dims.get("exploration_bonus", 0.1)
            # Prevent negative or 0 standard deviation
            std_dev = max(0.01, eb)
            sampled_score = random.normalvariate(ev, std_dev)
            sampled_candidates.append((item, sampled_score))
            
        sampled_candidates.sort(key=lambda x: x[1], reverse=True)
        selected_record = sampled_candidates[0][0]
        
    elif strategy == "ucb":
        # For UCB: ucb_score = aggregate_score + c * exploration_bonus
        # We use epsilon_t as the exploration multiplier c
        ucb_candidates = []
        for item in scored_candidates:
            c = item["candidate"]
            dims = getattr(c, "dimensions", {}) if isinstance(c, Candidate) else c.get("dimensions", {})
            eb = dims.get("exploration_bonus", 0.0)
            ucb_score = item["score"] + epsilon_t * eb
            ucb_candidates.append((item, ucb_score))
            
        ucb_candidates.sort(key=lambda x: x[1], reverse=True)
        selected_record = ucb_candidates[0][0]
        
    else:
        # Default fallback to exploitation
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        selected_record = scored_candidates[0]
        
    # Return selected candidate and scoring details for auditing
    scores_detail = []
    for item in scored_candidates:
        c = item["candidate"]
        name = getattr(c, "name", "unknown") if isinstance(c, Candidate) else c.get("name", "unknown")
        scores_detail.append({
            "name": name,
            "score": item["score"],
            "normalized": item["normalized"]
        })
        
    return selected_record["candidate"], scores_detail
