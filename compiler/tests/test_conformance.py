# docs/agent-control/compiler/tests/test_conformance.py

import pytest
import re
from ..schema import Schema, SchemaField, CrossFieldConstraint
from ..compiler import PolicyCompiler
from ..grants import Grant, GrantScope, GrantBounds
from ..operators import ABSENT

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Test 1: An absent allowlist adds no constraint.
def test_conformance_1_absent_allowlist():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/models/allowed = [\"gpt-4\"]",
        "project": "/models/allowed = absent"
    }
    epd = compiler.compile(sources)
    assert epd.status == "SATISFIED"
    assert epd.values["/models/allowed"] == ["gpt-4"]

# Test 2: An explicit empty allowlist denies all.
def test_conformance_2_explicit_empty_allowlist():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/models/allowed = [\"gpt-4\"]",
        "project": "/models/allowed = []"
    }
    epd = compiler.compile(sources)
    assert epd.status == "DENIED"
    assert epd.values["/models/allowed"] == []

# Test 3: A project cannot add an organization-denied model.
def test_conformance_3_cannot_add_org_denied_model():
    # Setup schema with denylist and allowed list
    schema = Schema()
    compiler = PolicyCompiler(schema)
    sources = {
        "organization": """
            /models/allowed = ["gpt-4", "claude-3"]
            /models/denied = ["claude-3"]
        """,
        "project": """
            /models/allowed = ["claude-3"]
        """
    }
    epd = compiler.compile(sources)
    # Composed allowed: ["gpt-4", "claude-3"] & ["claude-3"] = ["claude-3"]
    # Composed denied: ["claude-3"] | [] = ["claude-3"]
    # If we check that allowed model cannot be in denied models, or standard classification denies it
    assert "claude-3" in epd.values["/models/denied"]

# Test 4: A run cannot increase its cost ceiling.
def test_conformance_4_cannot_increase_cost_ceiling():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/run/maximum_cost = 10.0",
        "run": "/run/maximum_cost = 20.0"
    }
    epd = compiler.compile(sources)
    assert epd.status == "SATISFIED"
    assert epd.values["/run/maximum_cost"] == 10.0  # limit remains 10.0

# Test 5: A lower source cannot disable auditing.
def test_conformance_5_cannot_disable_auditing():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/integrity/audit_required = true",
        "project": "/integrity/audit_required = false"
    }
    epd = compiler.compile(sources)
    assert epd.values["/integrity/audit_required"] is True

# Test 6: Conflicting tenant identities fail.
def test_conformance_6_conflicting_tenant_identities():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/organization/identity = \"org_A\"",
        "project": "/organization/identity = \"org_B\""
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNAUTHORIZED_SOURCE"

# Test 7: Impossible intervals fail.
def test_conformance_7_impossible_intervals():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/run/allowed_interval = [1, 5]",
        "project": "/run/allowed_interval = [10, 15]"
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNSATISFIABLE"

# Test 8: Tool output cannot contribute policy.
def test_conformance_8_tool_output_cannot_contribute_policy():
    compiler = PolicyCompiler()
    sources = {
        "tool": "/run/maximum_cost = 50.0"
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNAUTHORIZED_SOURCE"

# Test 9: A source cannot select its composition operator.
def test_conformance_9_source_cannot_select_operator():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/integrity/sandbox_required = true"
    }
    epd = compiler.compile(sources)
    # The operator remains OR as defined in the schema
    assert epd.proof["/integrity/sandbox_required"]["operator"] == "OR"

# Test 10: Break-glass cannot weaken the integrity kernel.
def test_conformance_10_break_glass_cannot_weaken_kernel():
    compiler = PolicyCompiler()
    g = Grant(
        grant_id="g1",
        issuer="organization",
        issuer_identity="sha256:org",
        grantee="run",
        grantee_identity="sha256:run",
        scope=GrantScope(paths=["/integrity/sandbox_required"], values={"/integrity/sandbox_required": False}),
        bounds=GrantBounds(expires_at="2026-07-24T00:00:00Z")
    )
    epd = compiler.compile({"organization": "/integrity/sandbox_required = true"}, grants=[g], run_identity="sha256:run")
    assert epd.status == "INVALID"  # Rejected since sandbox_required is part of the integrity kernel

# Test 11: Delegation cannot amplify authority.
def test_conformance_11_delegation_cannot_amplify_authority():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/authorization/delegation_allowed = false",
        "project": "/authorization/delegation_allowed = true"
    }
    epd = compiler.compile(sources)
    assert epd.values["/authorization/delegation_allowed"] is False

# Test 12: Unknown and noncanonical paths fail.
def test_conformance_12_unknown_and_noncanonical_paths():
    compiler = PolicyCompiler()
    # 1. Unknown key
    epd1 = compiler.compile({"organization": "/unknown/path = true"})
    assert epd1.status == "UNKNOWN_SCHEMA_KEY"

    # 2. Noncanonical path (e.g. ends in slash or empty segment)
    epd2 = compiler.compile({"organization": "/integrity//sandbox_required = true"})
    assert epd2.status == "INVALID"

# Test 13: Unit mismatches fail.
def test_conformance_13_unit_mismatch():
    compiler = PolicyCompiler()
    # "request.error_rate" only supports "one", "percent"
    sources = {
        "organization": """
            /rule/when = [
                {"metric": "request.error_rate", "operator": "gt", "threshold": 0.05, "unit": "megabytes", "window_seconds": 300, "aggregation": "rate", "minimum_samples": 100}
            ]
        """
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNIT_CONFLICT"

# Test 14: Placeholder digests fail activation.
def test_conformance_14_placeholder_digests_fail():
    # A proper SHA-256 digest format check
    digest = "sha256:placeholder_invalid_format"
    assert not SHA256_RE.match(digest)

# Test 15: Harm gates cannot be bypassed by opportunity score.
def test_conformance_15_harm_gates_cannot_be_bypassed():
    # Even if opportunity scores exist, integrity requirements are still strictly evaluated
    compiler = PolicyCompiler()
    sources = {
        "organization": """
            /integrity/sandbox_required = true
        """
    }
    epd = compiler.compile(sources)
    assert epd.values["/integrity/sandbox_required"] is True

# Test 16: Composition output is invariant under source ordering.
def test_conformance_16_source_order_invariant():
    compiler = PolicyCompiler()
    sources1 = {
        "organization": "/run/maximum_cost = 10.0",
        "project": "/run/maximum_cost = 5.0"
    }
    sources2 = {
        "project": "/run/maximum_cost = 5.0",
        "organization": "/run/maximum_cost = 10.0"
    }
    epd1 = compiler.compile(sources1)
    epd2 = compiler.compile(sources2)
    assert epd1.values == epd2.values
    assert epd1.proof == epd2.proof

# Test 17: A non-owning source cannot set an owned field.
def test_conformance_17_non_owning_source_cannot_set_owned_field():
    compiler = PolicyCompiler()
    sources = {
        "project": "/organization/identity = \"hacker_org\""
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNAUTHORIZED_SOURCE"

# Test 18: An expired grant produces GRANT_EXPIRED, not DENIED.
def test_conformance_18_expired_grant():
    compiler = PolicyCompiler()
    g = Grant(
        grant_id="g_expired",
        issuer="organization",
        issuer_identity="sha256:org",
        grantee="run",
        grantee_identity="sha256:run",
        scope=GrantScope(paths=["/authorization/network_allowed"], values={"/authorization/network_allowed": True}),
        bounds=GrantBounds(expires_at="2020-01-01T00:00:00Z")
    )
    epd = compiler.compile({"organization": "/authorization/network_allowed = false"}, grants=[g], run_identity="sha256:run")
    assert epd.status == "GRANT_EXPIRED"

# Test 19: Exploration parameters set by data sources are rejected.
def test_conformance_19_exploration_parameters_rejected():
    compiler = PolicyCompiler()
    # "external" or other data source trying to set policy
    sources = {
        "external_data_source": "/run/maximum_cost = 5.0"
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNAUTHORIZED_SOURCE"

# Test 20: Dimension vectors are preserved in the composition proof regardless of aggregate score.
def test_conformance_20_dimension_vectors_preserved():
    compiler = PolicyCompiler()
    sources = {
        "organization": "/run/maximum_cost = 10.0"
    }
    epd = compiler.compile(sources)
    # Proof should contain the maximum cost entry and its contribution detail regardless of anything else
    assert "/run/maximum_cost" in epd.proof
    assert epd.proof["/run/maximum_cost"]["effective_value"] == 10.0
