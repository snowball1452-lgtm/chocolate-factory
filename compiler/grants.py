# docs/agent-control/compiler/grants.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

INTEGRITY_KERNEL_PATHS = {
    "/integrity/sandbox_required",
    "/integrity/tenant_isolation",
    "/integrity/break_glass_protection",
    "/integrity/audit_required",
    "/verification/policy/required",
    "/data/secrets/exposure_forbidden"
}

class GrantExpiredError(Exception):
    pass

class GrantRevokedError(Exception):
    pass

class InvalidGrantError(Exception):
    pass

@dataclass
class GrantScope:
    paths: List[str] = field(default_factory=list)
    expansion: str = "permit"  # permit, raise_bound
    values: Dict[str, Any] = field(default_factory=dict)  # values to inject for those paths

@dataclass
class GrantBounds:
    max_duration_seconds: int = 3600
    max_cost_delta: float = 100.0
    expires_at: str = "2026-07-24T00:00:00Z"

@dataclass
class GrantConstraints:
    integrity_kernel_non_overridable: bool = True
    audit_required: bool = True
    approval_required: bool = False

@dataclass
class Grant:
    grant_id: str
    issuer: str  # organization, etc.
    issuer_identity: str
    grantee: str  # run, etc.
    grantee_identity: str
    scope: GrantScope = field(default_factory=GrantScope)
    bounds: GrantBounds = field(default_factory=GrantBounds)
    constraints: GrantConstraints = field(default_factory=GrantConstraints)
    signature: Optional[str] = None
    revoked: bool = False

def parse_rfc3339(dt_str: str) -> datetime:
    # Handle Z suffix and fractional seconds if any
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)

def verify_and_activate_grant(
    grant: Grant,
    run_identity: str,
    current_time_str: str,
    revocation_registry: List[str],
    issuer_policies: Dict[str, Any]
) -> None:
    """
    Verifies a grant against current context.
    Raises GrantExpiredError, GrantRevokedError, or InvalidGrantError if verification fails.
    """
    # 1. Revocation check
    if grant.grant_id in revocation_registry or grant.revoked:
        raise GrantRevokedError(f"Grant {grant.grant_id} is revoked.")

    # 2. Expiration check
    current_time = parse_rfc3339(current_time_str)
    expiry_time = parse_rfc3339(grant.bounds.expires_at)
    if expiry_time <= current_time:
        raise GrantExpiredError(f"Grant {grant.grant_id} expired at {grant.bounds.expires_at}.")

    # 3. Grantee identity match
    if grant.grantee_identity != run_identity:
        raise InvalidGrantError(f"Grantee identity mismatch: expected {grant.grantee_identity}, got {run_identity}.")

    # 4. Integrity kernel check
    for path in grant.scope.paths:
        if path in INTEGRITY_KERNEL_PATHS:
            raise InvalidGrantError(f"Grant attempts to override integrity kernel path: {path}")

    # 5. Check issuer ceiling and possessions
    for path in grant.scope.paths:
        # Check if grant attempts to add allowlist entry issuer doesn't possess
        if path == "/models/allowed":
            grant_models = grant.scope.values.get(path, [])
            issuer_models = issuer_policies.get(path)
            # If issuer allows all (None/ABSENT), it is fine.
            # But if issuer restricts, grant cannot add models outside issuer's allowlist
            if issuer_models is not None:
                invalid_models = set(grant_models) - set(issuer_models)
                if invalid_models:
                    raise InvalidGrantError(
                        f"Grant cannot add allowlist entries issuer doesn't possess: {invalid_models}"
                    )
        # Check if grant attempts to raise maximum bound above issuer ceiling
        elif path == "/run/maximum_cost":
            grant_val = grant.scope.values.get(path)
            issuer_val = issuer_policies.get(path)
            if issuer_val is not None and grant_val is not None:
                if grant_val > issuer_val:
                    raise InvalidGrantError(
                        f"Grant cannot raise bound {path} to {grant_val} above issuer ceiling of {issuer_val}."
                    )
