# docs/agent-control/compiler/tests/test_grants.py

import pytest
from datetime import datetime
from ..schema import Schema, SchemaField
from ..compiler import PolicyCompiler
from ..grants import Grant, GrantScope, GrantBounds, GrantConstraints

def test_grant_expands_permissions():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    # Initial policy: network_allowed is False
    sources = {
        "organization": """
            /authorization/network_allowed = false
        """
    }

    # Grant: network_allowed = True
    g = Grant(
        grant_id="grant_1",
        issuer="organization",
        issuer_identity="sha256:org_key",
        grantee="run",
        grantee_identity="sha256:run_key",
        scope=GrantScope(paths=["/authorization/network_allowed"], expansion="permit", values={"/authorization/network_allowed": True}),
        bounds=GrantBounds(expires_at="2026-07-24T00:00:00Z")
    )

    epd = compiler.compile(
        sources,
        grants=[g],
        run_identity="sha256:run_key",
        current_time="2026-07-23T22:04:00Z"
    )

    assert epd.status == "SATISFIED"
    assert epd.values["/authorization/network_allowed"] is True

def test_expired_grant():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    sources = {
        "organization": "/authorization/network_allowed = false"
    }

    # Grant expired in 2025
    g = Grant(
        grant_id="grant_1",
        issuer="organization",
        issuer_identity="sha256:org_key",
        grantee="run",
        grantee_identity="sha256:run_key",
        scope=GrantScope(paths=["/authorization/network_allowed"], expansion="permit", values={"/authorization/network_allowed": True}),
        bounds=GrantBounds(expires_at="2025-07-24T00:00:00Z")
    )

    epd = compiler.compile(
        sources,
        grants=[g],
        run_identity="sha256:run_key",
        current_time="2026-07-23T22:04:00Z"
    )

    assert epd.status == "GRANT_EXPIRED"

def test_kernel_paths_non_overridable():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    sources = {
        "organization": "/integrity/sandbox_required = true"
    }

    # Grant tries to override sandbox_required (kernel path)
    g = Grant(
        grant_id="grant_1",
        issuer="organization",
        issuer_identity="sha256:org_key",
        grantee="run",
        grantee_identity="sha256:run_key",
        scope=GrantScope(paths=["/integrity/sandbox_required"], expansion="permit", values={"/integrity/sandbox_required": False}),
        bounds=GrantBounds(expires_at="2026-07-24T00:00:00Z")
    )

    epd = compiler.compile(
        sources,
        grants=[g],
        run_identity="sha256:run_key",
        current_time="2026-07-23T22:04:00Z"
    )

    assert epd.status == "INVALID"

def test_grant_cannot_raise_bound_above_issuer_ceiling():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    # Org ceiling is 10.0
    sources = {
        "organization": """
            /run/maximum_cost = 10.0
        """,
        "project": """
            /run/maximum_cost = 5.0
        """
    }

    # Grant tries to raise cost to 15.0 (which is above org ceiling of 10.0)
    g = Grant(
        grant_id="grant_1",
        issuer="organization",
        issuer_identity="sha256:org_key",
        grantee="run",
        grantee_identity="sha256:run_key",
        scope=GrantScope(paths=["/run/maximum_cost"], expansion="raise_bound", values={"/run/maximum_cost": 15.0}),
        bounds=GrantBounds(max_cost_delta=10.0, expires_at="2026-07-24T00:00:00Z")
    )

    epd = compiler.compile(
        sources,
        grants=[g],
        run_identity="sha256:run_key",
        current_time="2026-07-23T22:04:00Z"
    )

    assert epd.status == "INVALID"

def test_grant_cannot_add_allowlist_entries_issuer_doesnt_possess():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    # Org allowlist has "gpt-4" and "kimi-k2.6"
    sources = {
        "organization": """
            /models/allowed = ["gpt-4", "kimi-k2.6"]
        """,
        "project": """
            /models/allowed = ["gpt-4"]
        """
    }

    # Grant tries to add "claude-3" which is not in organization's allowlist
    g = Grant(
        grant_id="grant_1",
        issuer="organization",
        issuer_identity="sha256:org_key",
        grantee="run",
        grantee_identity="sha256:run_key",
        scope=GrantScope(paths=["/models/allowed"], expansion="permit", values={"/models/allowed": ["gpt-4", "claude-3"]}),
        bounds=GrantBounds(expires_at="2026-07-24T00:00:00Z")
    )

    epd = compiler.compile(
        sources,
        grants=[g],
        run_identity="sha256:run_key",
        current_time="2026-07-23T22:04:00Z"
    )

    assert epd.status == "INVALID"
