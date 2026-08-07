# docs/agent-control/compiler/operators.py

import json
from typing import Any, List, Dict, Union

class AbsentType:
    def __repr__(self):
        return "ABSENT"
    def __eq__(self, other):
        return isinstance(other, AbsentType)
    def __hash__(self):
        return hash("ABSENT")

ABSENT = AbsentType()

# Ordered floor ordering
DEFAULT_ORDERING = ["public", "internal", "confidential", "restricted"]

def get_order_idx(val: Any) -> int:
    if val in DEFAULT_ORDERING:
        return DEFAULT_ORDERING.index(val)
    try:
        # Try to match case-insensitively or return -1
        lower_vals = [x.lower() for x in DEFAULT_ORDERING]
        return lower_vals.index(val.lower())
    except Exception:
        return -1

def stable_rule_key(r: Dict[str, Any]) -> str:
    # Sort items and convert to stable string
    return str(sorted((k, str(v)) for k, v in r.items()))

def compose_values(op_type: str, a: Any, b: Any) -> Any:
    # 1. Handle Absence as identity element
    if a is ABSENT and b is ABSENT:
        return ABSENT
    if a is ABSENT:
        return b
    if b is ABSENT:
        return a

    # 2. Typed composition logic
    if op_type == "req_bool":
        return bool(a or b)
    elif op_type == "forbidden_bool":
        return bool(a or b)
    elif op_type == "perm_bool":
        return bool(a and b)
    elif op_type == "allowlist":
        # intersection
        set_a = set(a) if a is not None else set()
        set_b = set(b) if b is not None else set()
        # if one is None, wait: an absent allowlist is represented as ABSENT.
        # If it was explicit, it is a list (could be empty []).
        return sorted(list(set_a & set_b))
    elif op_type == "denylist":
        # union
        return sorted(list(set(a) | set(b)))
    elif op_type == "max_bound":
        return min(a, b)
    elif op_type == "min_bound":
        return max(a, b)
    elif op_type == "interval":
        # [low, high]
        return [max(a[0], b[0]), min(a[1], b[1])]
    elif op_type == "obligation_set":
        # union
        return sorted(list(set(a) | set(b)))
    elif op_type == "ordered_floor":
        idx_a = get_order_idx(a)
        idx_b = get_order_idx(b)
        return a if idx_a >= idx_b else b
    elif op_type == "predicate_rules":
        # list of rules. Deduplicate by stable key and sort
        combined = list(a) + list(b)
        seen = set()
        unique = []
        for r in combined:
            key = stable_rule_key(r)
            if key not in seen:
                seen.add(key)
                unique.append(r)
        # sort unique rules to guarantee stable ordering
        unique.sort(key=stable_rule_key)
        return unique
    else:
        raise ValueError(f"Unknown semantic type / operator type: {op_type}")

def is_less_permissive_or_equal(op_type: str, a: Any, b: Any) -> bool:
    """
    Returns True if policy A is no more permissive than policy B (A ⪯ B).
    Absence represents top element ⊤ (most permissive).
    Unsatisfiable/empty representation is bottom element ⊥ (least permissive).
    """
    if a is ABSENT and b is ABSENT:
        return True
    if a is ABSENT:
        # ABSENT is top (most permissive). It is only ⪯ ABSENT.
        return False
    if b is ABSENT:
        # Any present value is less permissive (or equal) than ABSENT.
        return True

    if op_type == "req_bool":
        # True (required) is more restrictive (less permissive) than False
        # A ⪯ B <=> a >= b
        return bool(a >= b)
    elif op_type == "forbidden_bool":
        # True (forbidden) is more restrictive (less permissive) than False
        # A ⪯ B <=> a >= b
        return bool(a >= b)
    elif op_type == "perm_bool":
        # False (no permission) is more restrictive (less permissive) than True
        # A ⪯ B <=> a <= b
        return bool(a <= b)
    elif op_type == "allowlist":
        # A ⪯ B <=> A is subset of B
        return set(a).issubset(set(b))
    elif op_type == "denylist":
        # A ⪯ B <=> B is subset of A (A denies more)
        return set(b).issubset(set(a))
    elif op_type == "max_bound":
        # A ⪯ B <=> a <= b (smaller max bound is less permissive)
        return bool(a <= b)
    elif op_type == "min_bound":
        # A ⪯ B <=> a >= b (larger min bound is less permissive)
        return bool(a >= b)
    elif op_type == "interval":
        # If A is unsatisfiable, it is bottom (least permissive), so A ⪯ B is always True.
        if a[0] > a[1]:
            return True
        # If B is unsatisfiable but A is not, A cannot be less permissive than B.
        if b[0] > b[1]:
            return False
        # A ⪯ B <=> A is subset of B
        return bool(a[0] >= b[0] and a[1] <= b[1])
    elif op_type == "obligation_set":
        # A ⪯ B <=> B is subset of A (A has more obligations)
        return set(b).issubset(set(a))
    elif op_type == "ordered_floor":
        # A ⪯ B <=> floor of A >= floor of B
        return bool(get_order_idx(a) >= get_order_idx(b))
    elif op_type == "predicate_rules":
        # A ⪯ B <=> B's rules is subset of A's rules (A has more rules)
        set_a = {stable_rule_key(r) for r in a}
        set_b = {stable_rule_key(r) for r in b}
        return set_b.issubset(set_a)
    else:
        raise ValueError(f"Unknown semantic type: {op_type}")
