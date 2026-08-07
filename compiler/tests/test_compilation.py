# docs/agent-control/compiler/tests/test_compilation.py

import pytest
from ..schema import Schema, SchemaField, CrossFieldConstraint
from ..compiler import PolicyCompiler
from ..operators import ABSENT

def test_full_compilation_success():
    schema = Schema()
    # Add a cross-field constraint
    schema.add_constraint(CrossFieldConstraint(
        id="duration-within-expiry",
        left="/run/maximum_duration",
        right="/authorization/expiry",
        operator="le"
    ))

    compiler = PolicyCompiler(schema)

    sources = {
        "organization": """
            /integrity/sandbox_required = true
            /authorization/expiry = 7200
            /models/allowed = ["gpt-4", "kimi-k2.6"]
            /organization/identity = "org_123"
        """,
        "project": """
            /run/maximum_duration = 3600
            /project/display_name = "project_alpha"
        """,
        "run": """
            /run/maximum_cost = 5.0
        """
    }

    epd = compiler.compile(sources)
    assert epd.status == "SATISFIED"
    assert epd.values["/integrity/sandbox_required"] is True
    assert epd.values["/authorization/expiry"] == 7200
    assert epd.values["/run/maximum_duration"] == 3600
    assert epd.values["/models/allowed"] == ["gpt-4", "kimi-k2.6"]
    assert epd.values["/organization/identity"] == "org_123"
    assert epd.values["/project/display_name"] == "project_alpha"
    assert epd.values["/run/maximum_cost"] == 5.0

def test_absence_and_explicit_empty_semantics():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    # 1. Project has "absent" allowed models
    sources_absent = {
        "organization": """
            /models/allowed = ["gpt-4", "kimi-k2.6"]
        """,
        "project": """
            /models/allowed = absent
        """
    }
    epd_absent = compiler.compile(sources_absent)
    assert epd_absent.status == "SATISFIED"
    assert epd_absent.values["/models/allowed"] == ["gpt-4", "kimi-k2.6"]

    # 2. Project has explicit empty allowlist []
    sources_empty = {
        "organization": """
            /models/allowed = ["gpt-4", "kimi-k2.6"]
        """,
        "project": """
            /models/allowed = []
        """
    }
    epd_empty = compiler.compile(sources_empty)
    # Status is DENIED because allowed models is empty
    assert epd_empty.status == "DENIED"
    assert epd_empty.values["/models/allowed"] == []

def test_owned_values_rejection():
    schema = Schema()
    compiler = PolicyCompiler(schema)

    # Non-owning source (project) tries to write /organization/identity
    sources = {
        "organization": """
            /organization/identity = "org_123"
        """,
        "project": """
            /organization/identity = "evil_identity_theft"
        """
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNAUTHORIZED_SOURCE"

def test_cross_field_constraint_violation():
    schema = Schema()
    schema.add_constraint(CrossFieldConstraint(
        id="duration-within-expiry",
        left="/run/maximum_duration",
        right="/authorization/expiry",
        operator="le"
    ))
    compiler = PolicyCompiler(schema)

    # Violation: duration is 10000, expiry is 7200
    sources = {
        "organization": """
            /authorization/expiry = 7200
        """,
        "project": """
            /run/maximum_duration = 10000
        """
    }
    epd = compiler.compile(sources)
    assert epd.status == "UNSATISFIABLE"
    assert "duration-within-expiry" in epd.metadata.get("error_message", "")
