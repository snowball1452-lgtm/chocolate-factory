# docs/agent-control/compiler/schema.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class SchemaField:
    name: str
    type: str  # req_bool, perm_bool, forbidden_bool, allowlist, denylist, max_bound, min_bound, interval, obligation_set, ordered_floor, predicate_rules, owned
    mode: str = "composed"  # composed, owned
    owner: Optional[str] = None  # organization, environment, project, run
    overridable: bool = False
    kernel: bool = False
    default: Any = None
    required: bool = False

@dataclass
class CrossFieldConstraint:
    id: str
    left: str
    right: str
    operator: str  # le, lt, ge, gt, eq, ne, subseteq, supports, permits
    on_violation: str = "UNSATISFIABLE"

class Schema:
    def __init__(self, identifier: str = "urn:agent-control:composition:2.0", version: str = "2.1.0", compatibility: str = "2.0"):
        self.identifier = identifier
        self.version = version
        self.compatibility = compatibility
        self.fields: Dict[str, SchemaField] = {}
        self.constraints: List[CrossFieldConstraint] = []
        self._add_default_fields()

    def add_field(self, f: SchemaField):
        self.fields[f.name] = f

    def add_constraint(self, c: CrossFieldConstraint):
        self.constraints.append(c)

    def _add_default_fields(self):
        # Integrity kernel fields (all are req_bool or forbidden_bool, kernel=True)
        self.add_field(SchemaField("/integrity/sandbox_required", "req_bool", kernel=True, default=True))
        self.add_field(SchemaField("/integrity/tenant_isolation", "req_bool", kernel=True, default=True))
        self.add_field(SchemaField("/integrity/break_glass_protection", "req_bool", kernel=True, default=True))
        self.add_field(SchemaField("/integrity/audit_required", "req_bool", kernel=True, default=True))
        self.add_field(SchemaField("/verification/policy/required", "req_bool", kernel=True, default=True))
        self.add_field(SchemaField("/data/secrets/exposure_forbidden", "forbidden_bool", kernel=True, default=False))

        # Permissions
        self.add_field(SchemaField("/authorization/network_allowed", "perm_bool", default=True))
        self.add_field(SchemaField("/authorization/external_writes_allowed", "perm_bool", default=True))
        self.add_field(SchemaField("/authorization/delegation_allowed", "perm_bool", default=True))

        # Collections
        self.add_field(SchemaField("/models/allowed", "allowlist", default=None))
        self.add_field(SchemaField("/models/denied", "denylist", default=[]))
        self.add_field(SchemaField("/verification/required_checks", "obligation_set", default=[]))

        # Bounds
        self.add_field(SchemaField("/run/maximum_duration", "max_bound", default=3600))
        self.add_field(SchemaField("/authorization/expiry", "max_bound", default=7200))
        self.add_field(SchemaField("/run/maximum_cost", "max_bound", default=10.0))
        self.add_field(SchemaField("/run/minimum_confidence", "min_bound", default=0.8))
        self.add_field(SchemaField("/run/allowed_interval", "interval", default=[0, 24]))

        # Ordered Floor
        self.add_field(SchemaField("/run/ordered_floor", "ordered_floor", default="public"))

        # Owned Fields (Factory Inventory)
        self.add_field(SchemaField("/organization/identity", "owned", mode="owned", owner="organization", overridable=False))
        self.add_field(SchemaField("/project/display_name", "owned", mode="owned", owner="project", overridable=False))
        self.add_field(SchemaField("/run/environment", "owned", mode="owned", owner="environment", overridable=False))

        # Structured Predicate Rules
        self.add_field(SchemaField("/rule/when", "predicate_rules", default=[]))

# Metric registry configuration
DEFAULT_METRIC_REGISTRY = {
    "version": "1.3.0",
    "signer": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "deprecation_grace_days": 90,
    "metrics": {
        "request.error_rate": {
            "description": "Fraction of requests returning 5xx",
            "valid_units": ["one", "percent"],
            "valid_operators": ["gt", "gte", "lt", "lte", "eq"],
            "valid_aggregations": ["rate", "avg", "p99"],
            "deprecated": False,
            "version": "1.0.0"
        },
        "system.cpu_usage": {
            "description": "CPU utilization fraction",
            "valid_units": ["one", "percent"],
            "valid_operators": ["gt", "gte", "lt", "lte", "eq"],
            "valid_aggregations": ["avg", "max"],
            "deprecated": False,
            "version": "1.0.0"
        }
    }
}

# External registry capability registries for cross-field constraint providers
DEFAULT_MODEL_CAPABILITY_REGISTRY = {
    "kimi-k2.6": {
        "capabilities": ["code_generation", "tool_use", "vision", "agent_swarm"],
        "max_context": 131072
    },
    "gpt-4": {
        "capabilities": ["code_generation", "tool_use"],
        "max_context": 8192
    }
}

DEFAULT_DATA_CLASSIFICATION_REGISTRY = {
    "public": {
        "permits_data": ["public"]
    },
    "internal": {
        "permits_data": ["public", "internal"]
    },
    "confidential": {
        "permits_data": ["public", "internal", "confidential"]
    },
    "restricted": {
        "permits_data": ["public", "internal", "confidential", "restricted"]
    }
}
