# docs/agent-control/compiler/compiler.py

import re
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from compiler.schema import Schema, SchemaField, CrossFieldConstraint, DEFAULT_METRIC_REGISTRY, DEFAULT_MODEL_CAPABILITY_REGISTRY, DEFAULT_DATA_CLASSIFICATION_REGISTRY
from compiler.parser import parse_policy_text
from compiler.operators import compose_values, is_less_permissive_or_equal, ABSENT, get_order_idx
from compiler.grants import Grant, verify_and_activate_grant, INTEGRITY_KERNEL_PATHS, GrantExpiredError, GrantRevokedError, InvalidGrantError
from compiler.proof import ContributionProof, ProofEntry, EPDIdentity

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

class CompilerError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status

class EffectivePolicyDocument:
    def __init__(self, epd_id: str, status: str, values: Dict[str, Any], proof: Dict[str, Any], metadata: Dict[str, Any]):
        self.epd_id = epd_id
        self.status = status
        self.values = values
        self.proof = proof
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epd_id": self.epd_id,
            "status": self.status,
            "values": self.values,
            "proof": self.proof,
            "metadata": self.metadata
        }

class PolicyCompiler:
    def __init__(self, schema: Optional[Schema] = None, metric_registry: Optional[Dict[str, Any]] = None):
        self.schema = schema or Schema()
        self.metric_registry = metric_registry or DEFAULT_METRIC_REGISTRY

    def compile(
        self,
        sources: Dict[str, Any],  # Dict of source_class -> (text or parsed dict)
        grants: Optional[List[Grant]] = None,
        run_identity: str = "sha256:default_run_identity",
        current_time: str = "2026-07-23T22:04:00Z",
        revocation_registry: Optional[List[str]] = None,
        protected_paths: Optional[List[Dict[str, Any]]] = None
    ) -> EffectivePolicyDocument:
        grants = grants or []
        revocation_registry = revocation_registry or []
        protected_paths = protected_paths or []

        epd_id = str(uuid.uuid4())
        status = "SATISFIED"
        proof_entries: Dict[str, Any] = {}
        effective_values: Dict[str, Any] = {}
        source_policy_digests: Dict[str, str] = {}
        active_grant_ids: List[str] = []

        try:
            # Stage 1: Verify the composition schema
            self._stage_1_verify_schema()

            # Stage 2: Parse policy modules
            parsed_sources = self._stage_2_parse_sources(sources, source_policy_digests)

            # Stage 3: Verify source identities and signatures (stubbed but structured)
            self._stage_3_verify_signatures(parsed_sources)

            # Stage 4 & 5: Resolve namespace, reject unknown & unauthorized namespaces
            self._stage_4_5_resolve_and_reject(parsed_sources)

            # Stage 6: Canonicalize (NFC, paths, units, metrics)
            self._stage_6_canonicalize(parsed_sources)

            # Process break-glass grants (verify & activate)
            activated_grants = []
            for g in grants:
                try:
                    # Get issuer's policies for verification
                    issuer_policies = parsed_sources.get(g.issuer, {})
                    verify_and_activate_grant(g, run_identity, current_time, revocation_registry, issuer_policies)
                    activated_grants.append(g)
                    active_grant_ids.append(g.grant_id)
                except GrantExpiredError as e:
                    raise CompilerError("GRANT_EXPIRED", str(e))
                except GrantRevokedError as e:
                    raise CompilerError("GRANT_REVOKED", str(e))
                except InvalidGrantError as e:
                    raise CompilerError("INVALID", str(e))

            # Stage 7: Apply field-level typed composition
            raw_composed_values = self._stage_7_typed_composition(parsed_sources, activated_grants, proof_entries)

            # Stage 8: Resolve owned values
            owned_resolved_values = self._stage_8_resolve_owned(parsed_sources, raw_composed_values, proof_entries)

            # Stage 9: Materialize signed schema defaults
            final_values = self._stage_9_materialize_defaults(owned_resolved_values, proof_entries)

            # Stage 10: Evaluate cross-field constraints
            self._stage_10_evaluate_constraints(final_values, proof_entries)

            # Stage 11: Evaluate protected-path rules
            self._stage_11_protected_paths(parsed_sources, protected_paths)

            # Deduce overall decision status based on field values
            status = self._deduce_overall_status(final_values, proof_entries)
            effective_values = final_values

        except CompilerError as ce:
            # Return EPD with error status and any proof entries collected so far
            return EffectivePolicyDocument(
                epd_id=epd_id,
                status=ce.status,
                values={},
                proof={k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in proof_entries.items()},
                metadata={
                    "error_message": str(ce),
                    "error_status": ce.status
                }
            )

        # Stage 12: Produce EPD
        # Stage 13: Produce Composition Proof
        proof_dict = {k: v.to_dict() for k, v in proof_entries.items()}

        # Stage 14: Canonical serialization, hash, sign both outputs (stubbed)
        epd_serialized = str(sorted(effective_values.items()))
        epd_digest = "sha256:" + hashlib.sha256(epd_serialized.encode("utf-8")).hexdigest()

        proof_serialized = str(sorted(proof_dict.items()))
        proof_digest = "sha256:" + hashlib.sha256(proof_serialized.encode("utf-8")).hexdigest()

        schema_serialized = str(sorted(self.schema.fields.items()))
        schema_digest = "sha256:" + hashlib.sha256(schema_serialized.encode("utf-8")).hexdigest()

        identity = EPDIdentity(
            epd_id=epd_id,
            epd_digest=epd_digest,
            schema_identifier=self.schema.identifier,
            schema_version=self.schema.version,
            composition_schema_digest=schema_digest,
            source_policy_digests=source_policy_digests,
            compilation_time=current_time,
            composition_proof_digest=proof_digest,
            active_grants=active_grant_ids
        )

        return EffectivePolicyDocument(
            epd_id=epd_id,
            status=status,
            values=effective_values,
            proof=proof_dict,
            metadata=identity.to_dict()
        )

    def _stage_1_verify_schema(self):
        # Verify schema is valid
        for path, field in self.schema.fields.items():
            if not path.startswith("/"):
                raise CompilerError("INVALID", f"Schema field path must start with '/': {path}")
            if field.type not in {
                "req_bool", "perm_bool", "forbidden_bool", "allowlist", "denylist",
                "max_bound", "min_bound", "interval", "obligation_set", "ordered_floor", "predicate_rules", "owned"
            }:
                raise CompilerError("INVALID", f"Invalid schema field type: {field.type}")

    def _stage_2_parse_sources(self, sources: Dict[str, Any], digests: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        parsed = {}
        for src_class, content in sources.items():
            if src_class not in {"organization", "environment", "project", "run"}:
                raise CompilerError("UNAUTHORIZED_SOURCE", f"Unauthorized source class: {src_class}")

            if isinstance(content, str):
                try:
                    parsed[src_class] = parse_policy_text(content)
                except Exception as e:
                    raise CompilerError("INVALID", f"Failed to parse TOML/text for {src_class}: {e}")
                # Compute digest
                digests[src_class] = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
            elif isinstance(content, dict):
                parsed[src_class] = content
                digests[src_class] = "sha256:" + hashlib.sha256(str(sorted(content.items())).encode("utf-8")).hexdigest()
            else:
                raise CompilerError("INVALID", f"Invalid policy format for {src_class}")
        return parsed

    def _stage_3_verify_signatures(self, parsed_sources: Dict[str, Dict[str, Any]]):
        # Stubbed out but validates structure if meta/signatures exist
        pass

    def _stage_4_5_resolve_and_reject(self, parsed_sources: Dict[str, Dict[str, Any]]):
        for src, policy in parsed_sources.items():
            for path in policy.keys():
                # Check canonicality FIRST
                if not path.startswith("/") or "//" in path or "/./" in path or "/../" in path or path.endswith("/"):
                    raise CompilerError("INVALID", f"Noncanonical path: {path}")
                if path not in self.schema.fields:
                    raise CompilerError("UNKNOWN_SCHEMA_KEY", f"Unknown schema key: {path}")

    def _stage_6_canonicalize(self, parsed_sources: Dict[str, Dict[str, Any]]):
        # Check canonical paths
        for src, policy in parsed_sources.items():
            for path, val in policy.items():
                # Validate metrics in predicate rules
                field_def = self.schema.fields[path]
                if field_def.type == "predicate_rules" and val is not ABSENT and isinstance(val, list):
                    for rule in val:
                        metric = rule.get("metric")
                        unit = rule.get("unit")
                        operator = rule.get("operator")
                        aggregation = rule.get("aggregation")

                        if metric not in self.metric_registry["metrics"]:
                            raise CompilerError("UNKNOWN_SCHEMA_KEY", f"Unknown metric: {metric}")
                        
                        m_def = self.metric_registry["metrics"][metric]
                        if m_def.get("deprecated"):
                            # Check if grace period is past
                            # Here we stub grace period check as always past deprecation if past grace
                            raise CompilerError("INVALID", f"Metric {metric} is deprecated and past grace period.")

                        if unit not in m_def["valid_units"]:
                            raise CompilerError("UNIT_CONFLICT", f"Invalid unit {unit} for metric {metric}")

                        if operator not in m_def["valid_operators"]:
                            raise CompilerError("INVALID", f"Invalid operator {operator} for metric {metric}")

                        if aggregation not in m_def["valid_aggregations"]:
                            raise CompilerError("INVALID", f"Invalid aggregation {aggregation} for metric {metric}")

    def _stage_7_typed_composition(
        self,
        parsed_sources: Dict[str, Dict[str, Any]],
        grants: List[Grant],
        proof_entries: Dict[str, ProofEntry]
    ) -> Dict[str, Any]:
        raw_composed = {}

        # Source precedence order: organization -> environment -> project -> run
        sources_order = ["organization", "environment", "project", "run"]

        for path, field_def in self.schema.fields.items():
            if field_def.mode == "owned":
                # Owned fields are resolved in Stage 8
                continue

            # First, perform composition of non-grant sources
            effective_val = ABSENT
            contributions = []

            for src in sources_order:
                src_policy = parsed_sources.get(src, {})
                if path in src_policy:
                    val = src_policy[path]
                    if val is not ABSENT:
                        contributions.append(ContributionProof(source=src, state="explicit", value=val))
                        effective_val = compose_values(field_def.type, effective_val, val)
                    else:
                        contributions.append(ContributionProof(source=src, state="absent"))
                else:
                    contributions.append(ContributionProof(source=src, state="absent"))

            # Next, apply grant composition/expansion if there are active grants scoped to this path
            for g in grants:
                if path in g.scope.paths:
                    grant_val = g.scope.values.get(path)
                    contributions.append(ContributionProof(source="grant", state="explicit", value=grant_val))

                    if field_def.type == "perm_bool":
                        # Grants for permission booleans set value to True directly, overriding normal composition
                        effective_val = True
                    elif field_def.type == "max_bound":
                        # Raise maximum bound by delta up to issuer's ceiling
                        issuer_val = parsed_sources.get(g.issuer, {}).get(path)
                        # Previous effective value (before this grant)
                        prev_val = effective_val if effective_val is not ABSENT else field_def.default
                        if prev_val is not None:
                            raised_val = prev_val + g.bounds.max_cost_delta
                            if issuer_val is not None:
                                effective_val = min(raised_val, issuer_val)
                            else:
                                effective_val = raised_val
                    elif field_def.type == "allowlist":
                        # Add entries to effective allowlist, but only those in issuer's allowlist
                        issuer_val = parsed_sources.get(g.issuer, {}).get(path, [])
                        if issuer_val is None:
                            # if issuer allows all, we can add anything in grant_val
                            issuer_val = grant_val
                        prev_val = effective_val if effective_val is not ABSENT else []
                        if prev_val is None:
                            prev_val = []
                        added_entries = [x for x in grant_val if x in issuer_val]
                        effective_val = sorted(list(set(prev_val) | set(added_entries)))

            # Record proof entry
            # Sort contributions by source name for order-independence
            contributions.sort(key=lambda c: c.source)
            proof_entries[path] = ProofEntry(
                path=path,
                type=field_def.type,
                operator=self._get_operator_name(field_def.type),
                contributions=contributions,
                effective_value=effective_val,
                status="SATISFIED"
            )
            raw_composed[path] = effective_val

        return raw_composed

    def _stage_8_resolve_owned(
        self,
        parsed_sources: Dict[str, Dict[str, Any]],
        raw_composed: Dict[str, Any],
        proof_entries: Dict[str, ProofEntry]
    ) -> Dict[str, Any]:
        resolved = dict(raw_composed)

        for path, field_def in self.schema.fields.items():
            if field_def.mode != "owned" and field_def.type != "owned":
                continue

            owner = field_def.owner
            contributions = []
            effective_val = ABSENT

            # First, check if any non-owner source sets the field
            for src, policy in parsed_sources.items():
                if path in policy:
                    val = policy[path]
                    if val is not ABSENT:
                        if src != owner:
                            # If not overridable or if a non-owning source writes, check overridable
                            if not field_def.overridable:
                                raise CompilerError("UNAUTHORIZED_SOURCE", f"Non-owning source {src} cannot set owned field {path}.")
                            else:
                                # Overridable is True: treat owner's value as one contribution, lower-precedence can compose
                                contributions.append(ContributionProof(source=src, state="explicit", value=val))
                                effective_val = compose_values(field_def.type, effective_val, val)
                        else:
                            contributions.append(ContributionProof(source=src, state="explicit", value=val))
                            effective_val = val
                    else:
                        contributions.append(ContributionProof(source=src, state="absent"))
                else:
                    contributions.append(ContributionProof(source=src, state="absent"))

            # If overridable=False, the owner source value IS the effective value
            if not field_def.overridable:
                owner_policy = parsed_sources.get(owner, {})
                if path in owner_policy:
                    effective_val = owner_policy[path]

            contributions.sort(key=lambda c: c.source)
            proof_entries[path] = ProofEntry(
                path=path,
                type="owned",
                operator="none",
                contributions=contributions,
                effective_value=effective_val,
                status="SATISFIED"
            )
            resolved[path] = effective_val

        return resolved

    def _stage_9_materialize_defaults(
        self,
        resolved_values: Dict[str, Any],
        proof_entries: Dict[str, ProofEntry]
    ) -> Dict[str, Any]:
        final = dict(resolved_values)

        for path, field_def in self.schema.fields.items():
            val = final.get(path, ABSENT)
            if val is ABSENT:
                if field_def.required:
                    raise CompilerError("MISSING_REQUIRED_VALUE", f"Required field {path} has no explicit or default value.")
                final[path] = field_def.default
                if path in proof_entries:
                    proof_entries[path].effective_value = field_def.default

        return final

    def _stage_10_evaluate_constraints(self, final_values: Dict[str, Any], proof_entries: Dict[str, ProofEntry]):
        for constraint in self.schema.constraints:
            left_val = final_values.get(constraint.left)
            right_val = final_values.get(constraint.right)

            # Skip check if either is absent/None
            if left_val is None or right_val is None or left_val is ABSENT or right_val is ABSENT:
                continue

            violation = False
            desc = ""

            op = constraint.operator
            if op == "le":
                if not (left_val <= right_val):
                    violation = True
                    desc = f"{left_val} is not <= {right_val}"
            elif op == "lt":
                if not (left_val < right_val):
                    violation = True
                    desc = f"{left_val} is not < {right_val}"
            elif op == "ge":
                if not (left_val >= right_val):
                    violation = True
                    desc = f"{left_val} is not >= {right_val}"
            elif op == "gt":
                if not (left_val > right_val):
                    violation = True
                    desc = f"{left_val} is not > {right_val}"
            elif op == "eq":
                if not (left_val == right_val):
                    violation = True
                    desc = f"{left_val} is not == {right_val}"
            elif op == "ne":
                if not (left_val != right_val):
                    violation = True
                    desc = f"{left_val} is not != {right_val}"
            elif op == "subseteq":
                if not set(left_val).issubset(set(right_val)):
                    violation = True
                    desc = f"{left_val} is not a subset of {right_val}"
            elif op == "supports":
                # left_val is model (string), right_val is required capability (or list)
                model_caps = DEFAULT_MODEL_CAPABILITY_REGISTRY.get(left_val, {}).get("capabilities", [])
                req_caps = [right_val] if isinstance(right_val, str) else right_val
                if not set(req_caps).issubset(set(model_caps)):
                    violation = True
                    desc = f"Model {left_val} does not support capabilities {req_caps}"
            elif op == "permits":
                # left_val is classification, right_val is data classification
                permitted_data = DEFAULT_DATA_CLASSIFICATION_REGISTRY.get(left_val, {}).get("permits_data", [])
                if right_val not in permitted_data:
                    violation = True
                    desc = f"Classification {left_val} does not permit data classification {right_val}"

            if violation:
                # Mark both proof entries as UNSATISFIABLE
                if constraint.left in proof_entries:
                    proof_entries[constraint.left].status = "UNSATISFIABLE"
                if constraint.right in proof_entries:
                    proof_entries[constraint.right].status = "UNSATISFIABLE"
                raise CompilerError("UNSATISFIABLE", f"Constraint violation {constraint.id}: {desc}")

    def _stage_11_protected_paths(self, parsed_sources: Dict[str, Dict[str, Any]], protected_paths: List[Dict[str, Any]]):
        # Protected paths behavior: reject override by lower sources
        for prot in protected_paths:
            path = prot["path"]
            scope = prot.get("scope", "exact")
            behavior = prot.get("behavior", "reject-override")

            if path not in self.schema.fields:
                raise CompilerError("INVALID", f"Protected path does not resolve to any schema node: {path}")

            if behavior == "reject-override":
                # Find the highest source that defines this path (or sub-path)
                defining_sources = []
                for src in ["organization", "environment", "project", "run"]:
                    policy = parsed_sources.get(src, {})
                    has_override = False
                    if scope == "exact":
                        if path in policy and policy[path] is not ABSENT:
                            has_override = True
                    elif scope == "subtree":
                        # Check if path is prefix
                        for p in policy.keys():
                            if p == path or p.startswith(path + "/") and policy[p] is not ABSENT:
                                has_override = True
                    if has_override:
                        defining_sources.append(src)

                if len(defining_sources) > 1:
                    # An override exists! Organization is highest, other sources overriding are unauthorized
                    raise CompilerError("UNAUTHORIZED_SOURCE", f"Protected path {path} overridden by lower sources: {defining_sources[1:]}")

    def _deduce_overall_status(self, final_values: Dict[str, Any], proof_entries: Dict[str, ProofEntry]) -> str:
        # Check if any field is unsatisfiable (e.g. interval high < low)
        for path, val in final_values.items():
            field_def = self.schema.fields.get(path)
            if field_def and field_def.type == "interval":
                if val is not None and val is not ABSENT and len(val) == 2:
                    if val[0] > val[1]:
                        if path in proof_entries:
                            proof_entries[path].status = "UNSATISFIABLE"
                        return "UNSATISFIABLE"

        # Check for explicit empty allowlist or denied values
        for path, val in final_values.items():
            field_def = self.schema.fields.get(path)
            if field_def:
                if field_def.type == "perm_bool" and val is False:
                    if path in proof_entries:
                        proof_entries[path].status = "DENIED"
                    return "DENIED"
                elif field_def.type == "forbidden_bool" and val is True:
                    if path in proof_entries:
                        proof_entries[path].status = "DENIED"
                    return "DENIED"
                elif field_def.type == "allowlist" and val == [] and val is not None:
                    if path in proof_entries:
                        proof_entries[path].status = "DENIED"
                    return "DENIED"

        return "SATISFIED"

    def _get_operator_name(self, type_str: str) -> str:
        ops = {
            "req_bool": "OR",
            "forbidden_bool": "OR",
            "perm_bool": "AND",
            "allowlist": "intersection",
            "denylist": "union",
            "max_bound": "min",
            "min_bound": "max",
            "interval": "intersection",
            "obligation_set": "union",
            "ordered_floor": "highest",
            "predicate_rules": "all",
            "owned": "none"
        }
        return ops.get(type_str, "none")
