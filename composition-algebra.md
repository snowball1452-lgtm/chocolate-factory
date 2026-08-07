# Agent-Control Policy Composition Algebra

**Status**: Stable / Approved for v2.0  
**Version**: 2.1.0 (addendum appended)  
**Namespace**: `agent-control`  
**Schema compatibility**: 2.0  
**Effective date**: 2026-07-23

---

## 1. Purpose

This document defines how `agent-control` policy sources compose into one **Effective Policy Document (EPD)**.

Composition **MUST** be:

- deterministic;
- fail-closed;
- monotonic for security constraints;
- independent of source loading order;
- explainable;
- globally namespaced;
- schema-typed.

Policy files provide values. A signed composition schema defines the operator and type of every policy path.

**A policy source MUST NOT select its own composition operator.**

---

## 2. Normative language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119).

---

## 3. Semantic model

Let:

- `Ω` be the set of all possible executions;
- `⟦P⟧` be the executions permitted by policy `P`;
- `A ⪯ B` mean that `A` is **no more permissive** than `B`.

Therefore:

```
A ⪯ B iff ⟦A⟧ ⊆ ⟦B⟧
```

Ordinary policy composition is **intersection**:

```
⟦A ⊓ B⟧ = ⟦A⟧ ∩ ⟦B⟧
```

The meet operator `⊓` **MUST** satisfy:

| Property | Definition |
| :--- | :--- |
| **Commutativity** | `A ⊓ B = B ⊓ A` |
| **Associativity** | `(A ⊓ B) ⊓ C = A ⊓ (B ⊓ C)` |
| **Idempotence** | `A ⊓ A = A` |
| **Restriction** | `A ⊓ B ⪯ A` and `A ⊓ B ⪯ B` |

- `⊤` represents **no additional constraint**.
- `⊥` represents **no permitted execution** (empty set).

```
P ⊓ ⊤ = P
P ⊓ ⊥ = ⊥
```

---

## 4. Global namespace

All policy modules contribute to one global policy namespace.

**Examples**:
- `/integrity/sandbox_required`
- `/authorization/default_effect`
- `/data/secrets/store_in_prompt`
- `/models/allowed`
- `/verification/policy/required`

> File names (e.g., `integrity.toml`, `models.toml`) are **not** part of policy paths.

### 4.1 Canonical paths

Policy paths **MUST**:

- begin with `/`;
- use `/` as the segment separator;
- use case-sensitive schema keys;
- use Unicode NFC normalization;
- contain no empty, `.` or `..` segments;
- resolve to a known schema node.

Unknown and noncanonical paths **MUST** be rejected.

### 4.2 Protected paths

Protected paths **MUST** use explicit scope:

```toml
[[governance.protections]]
path = "/integrity/tenancy"
scope = "subtree"   # "exact" or "subtree"
behavior = "reject-override"
```

Valid scopes are:

- exact;
- subtree.

Glob, prefix, wildcard, and regular-expression protection paths are forbidden.

A protection path that resolves to no schema node MUST be rejected.

---

## 5. Policy sources

Recognized source classes are:

1. organization;
2. environment;
3. project;
4. authorized run request.

The following are data sources, not policy sources:

- external content;
- retrieved content;
- retrieved memory;
- agent-authored memory;
- delegated instructions;
- model output;
- tool output.

Data sources MAY propose policy changes. They MUST NOT directly contribute effective policy.

Every contribution MUST record:

- source class;
- source identity;
- policy version;
- content digest;
- signature status;
- activation status.

Unauthorized namespace contributions MUST be rejected before composition.

---

## 6. Absence

An absent value means:

No constraint contributed by this source.

Absence is the identity element ⊤ for composition.

Absence MUST NOT be interpreted as:

- false;
- 0;
- an empty string;
- an empty collection;
- a schema default.

Explicit empty collections and explicit Boolean values are real policy values.

Example (Allowlist):

```
Organization allowed models: ["a", "b"]
Project allowed models: absent
Effective models: ["a", "b"]
```

Counterexample:

```
Organization allowed models: ["a", "b"]
Project allowed models: []
Effective models: []   # Explicit empty list means "allow nothing"
```

Schema defaults MUST be materialized only after source composition.

---

## 7. Typed operators

Every composable field MUST have one schema-defined semantic type.

### 7.1 Required Boolean

A required Boolean uses OR:

```
compose(a, b) = a OR b
absence = false
```

Examples:

- sandbox_required
- audit_required
- approval_required

If any source requires the control, the control is required.

### 7.2 Forbidden Boolean

A forbidden Boolean uses OR:

```
compose(a, b) = a OR b
absence = false
```

Examples:

- approval_bypass_forbidden
- secret_exposure_forbidden

If any source forbids the action, the action is forbidden.

### 7.3 Permission Boolean

A permission Boolean uses AND:

```
compose(a, b) = a AND b
absence = true
```

Examples:

- network_allowed
- external_writes_allowed
- delegation_allowed

If any source refuses permission, permission is refused.

Note: Fields named `enabled` MUST be classified explicitly. The name alone does not determine whether the field is a requirement or a permission.

### 7.4 Allowlist

Allowlists use set intersection:

```
compose(A, B) = A ∩ B
absence = universal authorized set
```

The compiler SHOULD implement absence by skipping that contribution.

An explicit empty allowlist permits nothing.

### 7.5 Denylist

Denylists use set union:

```
compose(A, B) = A ∪ B
absence = ∅
```

### 7.6 Maximum bound

Maximum bounds use minimum:

```
compose(a, b) = min(a, b)
absence = +∞
```

Examples:

- maximum cost;
- maximum duration;
- maximum iterations;
- maximum concurrency;
- maximum delegation depth;
- maximum retention.

### 7.7 Minimum bound

Minimum bounds use maximum:

```
compose(a, b) = max(a, b)
absence = -∞
```

Examples:

- minimum pass rate;
- minimum confidence;
- minimum reviewers;
- minimum observation period.

### 7.8 Interval

Intervals use intersection:

```
[a₁, a₂] ⊓ [b₁, b₂] = [max(a₁, b₁), min(a₂, b₂)]
```

If the resulting lower bound exceeds the upper bound, the result is UNSATISFIABLE.

### 7.9 Obligation set

Obligations use set union:

```
compose(A, B) = A ∪ B
absence = ∅
```

Examples:

- required verification checks;
- required approvals;
- required audit events;
- required attestations.

### 7.10 Ordered floor

An ordered floor selects the highest required value.

Example order:

```text
public < internal < confidential < restricted
```

If one source requires internal and another requires restricted, the effective value is restricted.

### 7.11 Predicate rules (structured conditions)

Expression strings (e.g., "cpu > 80%") are forbidden in policy sources.

Instead, use structured rules:

```toml
[[rule.when]]
metric = "request.error_rate"
operator = "gt"
threshold = 0.05
unit = "one"
window_seconds = 300
aggregation = "rate"
minimum_samples = 100
```

A predicate MUST identify:

- metric;
- operator;
- threshold;
- unit;
- window;
- aggregation;
- minimum sample count.

Allowed compound operators are:

- all;
- any.

Independent policy-source requirements MUST compose using all.

Metric identifiers and units MUST resolve through a signed metric registry. Unknown metrics, unsupported operators, and unit mismatches MUST be rejected.

### 7.12 Owned values ("Factory Inventory")

Some schema fields are **owned**, not composed. An owned field is set directly by the source that has authority over it — it bypasses the typed composition operator.

The composition schema MUST declare each field as either `composed` or `owned`.

An owned field MUST declare:

- the authorized source class that sets it;
- whether lower-precedence sources MAY override (default: no).

```toml
[schema.fields."/organization/identity"]
type = "string"
mode = "owned"
owner = "organization"
overridable = false
```

If a non-owning source contributes a value to an owned field, the compiler MUST reject it as UNAUTHORIZED_SOURCE.

If the owning source is absent, the compiler MUST treat the field as MISSING_REQUIRED_VALUE if the schema marks it required, or use the signed schema default if one exists.

Owned values resolve at compilation stage 8, after field-level composition (stage 7) and before schema default materialization (stage 9).

Rationale: Organization identity, environment name, and similar identity fields are not something you "compose" — they are declared by their owner. Conflating owned and composed fields was the source of ambiguity flagged by review question #4.

---

## 8. Cross-field constraints ("The Contract Room")

Field-level composition MUST be followed by cross-field validation.

### 8.1 Constraint declaration

Cross-field constraints MUST be declared in the signed composition schema, not in policy source files.

```toml
[[schema.constraints]]
id = "duration-within-deadline"
left = "/run/maximum_duration"
right = "/authorization/expiry"
operator = "le"
on_violation = "UNSATISFIABLE"
```

### 8.2 Constraint operators

| Operator | Meaning |
| :--- | :--- |
| `le` | left ≤ right |
| `lt` | left < right |
| `ge` | left ≥ right |
| `gt` | left > right |
| `eq` | left = right |
| `ne` | left ≠ right |
| `subseteq` | left ⊆ right |
| `supports` | left (model) supports right (toolset) — resolves through model registry |
| `permits` | left (classification) permits right (data classification) — resolves through classification registry |

### 8.3 Evaluation

Constraints MUST be evaluated after stage 7 (field-level composition) and stage 8 (owned value resolution), using the effective values of both fields.

A constraint violation MUST produce UNSATISFIABLE with a proof entry identifying:

- constraint id;
- left path and effective value;
- right path and effective value;
- operator;
- violation description.

The compiler MUST NOT silently choose one conflicting field.

### 8.4 Registry-backed constraints

The `supports` and `permits` operators require external registries:

- `supports` resolves through a signed model capability registry (which models support which tools).
- `permits` resolves through a signed data classification registry (which classification levels permit which data categories).

These registries MUST be versioned and signed. The compiler MUST record the registry version used in the composition proof.

---

## 9. Taste and opportunity ranking ("The Tasting Room")

Taste and opportunity ranking occur only after integrity, authorization, and verification eligibility gates.

Safety MUST NOT be represented solely as a negative ranking weight.

### 9.1 Eligibility gates

A candidate is eligible only if:

```
integrity passes
AND authorization passes
AND required evidence exists
AND harm upper confidence bound ≤ maximum harm
AND catastrophic risk ≤ maximum catastrophic risk
```

Ineligible candidates MUST NOT be rescued by high expected upside.

### 9.2 Ranking dimensions

After eligibility, candidates MAY be ranked along authorized dimensions. Each dimension MUST be:

- declared in the signed composition schema;
- bounded (defined range);
- authorized (weights set by policy, not ad hoc);
- auditable (the dimension vector MUST be preserved in the composition proof).

Minimum required dimensions:

| Dimension | Range | Direction | Description |
| :--- | :--- | :--- | :--- |
| `expected_value` | [0, 1] | higher better | Estimated utility of the action |
| `novelty` | [0, 1] | higher better | How different from prior executions |
| `exploration_bonus` | [0, 1] | higher better | Information gain / discovery potential |
| `playfulness` | [0, 1] | higher better | Engagement, surprise, delight potential |
| `cost` | [0, +∞) | lower better | Resource cost |
| `harm_upper_bound` | [0, 1] | lower better | Upper confidence bound on harm |

The schema MAY declare additional dimensions. Undeclared dimensions MUST be rejected.

### 9.3 Weight authorization

Dimension weights MUST be set by policy sources, not computed at runtime.

```toml
[taste.weights]
expected_value = 0.30
novelty = 0.20
exploration_bonus = 0.25
playfulness = 0.15
cost = 0.10
harm_upper_bound = 0.00   # Harm is a gate, not a weight
```

Weights compose as **ordered floor** (highest required weight wins) across policy sources. A lower-precedence source MAY NOT reduce a weight set by a higher-precedence source.

If `harm_upper_bound` has a non-zero weight, the compiler MUST emit a warning: harm SHOULD be a gate, not a ranking signal.

### 9.4 Aggregate score

The aggregate score is a weighted sum of normalized dimension values:

```
score = Σ(weight_i × normalize(dimension_i))
```

The aggregate score MAY be used to order eligible candidates. The engine MUST preserve the underlying dimension vector and MUST NOT treat the aggregate score as verification evidence.

### 9.5 Exploration policy

The composition schema MAY declare an exploration policy that controls how the ranking system balances exploitation (known-good actions) vs exploration (novel actions).

```toml
[taste.exploration]
strategy = "epsilon-greedy"   # or "thompson-sampling" or "ucb"
epsilon = 0.15                  # for epsilon-greedy
annealing = "linear"           # "linear", "exponential", "none"
floor = 0.05                   # minimum epsilon after annealing
```

The exploration policy MUST be authorized through normal policy composition. Data sources (model output, tool output) MUST NOT set exploration parameters.

---

## 10. Placeholder rejection

Activation mode MUST reject:

- unresolved references;
- placeholder digests;
- malformed digests;
- expired authorizations;
- missing trust material;
- invalid timestamps;
- placeholder identities.

A SHA-256 digest MUST match:

```regex
^sha256:[0-9a-f]{64}$
```

Activation timestamps MUST use RFC 3339 with an explicit timezone.

Lint mode MAY report placeholders without activation. Activation mode MUST treat them as fatal.

---

## 11. Compilation stages

The compiler MUST perform these stages in order:

1. Verify the composition schema.
2. Parse policy modules.
3. Verify source identities and signatures.
4. Resolve contributions into the global namespace.
5. Reject unknown keys and unauthorized namespaces.
6. Canonicalize paths, values, units, and identities.
7. Apply field-level typed composition.
8. Resolve owned values.
9. Materialize signed schema defaults.
10. Evaluate cross-field constraints.
11. Evaluate protected-path rules.
12. Produce the Effective Policy Document.
13. Produce the Policy Composition Proof.
14. Canonically serialize, hash, and sign both outputs.

Tools MUST consume the compiled effective policy or a scoped decision derived from it. Tools SHOULD NOT independently merge source TOML files.

---

## 12. Result states

Compilation and authorization MUST distinguish these states:

| State | Description |
| :--- | :--- |
| SATISFIED | Policy compiles and permits the action. |
| DENIED | Policy compiles but explicitly denies the action. |
| UNSATISFIABLE | Conflicting constraints make the policy impossible. |
| INVALID | Schema violation or malformed input. |
| UNAUTHORIZED_SOURCE | Source lacks authority to contribute. |
| UNKNOWN_SCHEMA_KEY | Path does not exist in the schema. |
| MISSING_REQUIRED_VALUE | A required field has no explicit or default value. |
| IDENTITY_CONFLICT | Conflicting identity claims. |
| UNIT_CONFLICT | Incompatible units in a predicate. |
| EXPIRED | Expired authorization or timestamp. |
| UNRESOLVED_REFERENCE | A reference cannot be resolved. |
| GRANT_EXPIRED | A break-glass grant has expired (see Section 19). |
| GRANT_REVOKED | A break-glass grant was revoked (see Section 19). |

An empty effective allowlist is normally DENIED. An impossible interval is UNSATISFIABLE.

---

## 13. Composition proof

Every effective value MUST include:

- canonical path;
- semantic type;
- operator;
- source contributions;
- explicit or absent state;
- effective value;
- decision status;
- source digests.

Example:

```json
{
  "path": "/models/allowed",
  "type": "allowlist",
  "operator": "intersection",
  "contributions": [
    {
      "source": "organization",
      "state": "explicit",
      "value": ["a", "b"]
    },
    {
      "source": "environment",
      "state": "absent"
    },
    {
      "source": "project",
      "state": "explicit",
      "value": ["b"]
    }
  ],
  "effective_value": ["b"],
  "status": "SATISFIED"
}
```

---

## 14. Required algebra tests

Every restrictive operator MUST pass:

```
compose(A, B) = compose(B, A)
compose(compose(A, B), C) = compose(A, compose(B, C))
compose(A, A) = A
compose(A, B) ⪯ A
compose(A, B) ⪯ B
```

The conformance suite MUST also test:

1. An absent allowlist adds no constraint.
2. An explicit empty allowlist denies all.
3. A project cannot add an organization-denied model.
4. A run cannot increase its cost ceiling.
5. A lower source cannot disable auditing.
6. Conflicting tenant identities fail.
7. Impossible intervals fail.
8. Tool output cannot contribute policy.
9. A source cannot select its composition operator.
10. Break-glass cannot weaken the integrity kernel.
11. Delegation cannot amplify authority.
12. Unknown and noncanonical paths fail.
13. Unit mismatches fail.
14. Placeholder digests fail activation.
15. Harm gates cannot be bypassed by opportunity score.
16. Composition output is invariant under source ordering.
17. A non-owning source cannot set an owned field.
18. An expired grant produces GRANT_EXPIRED, not DENIED.
19. Exploration parameters set by data sources are rejected.
20. Dimension vectors are preserved in the composition proof regardless of aggregate score.

---

## 15. Effective-policy identity

Every Effective Policy Document MUST record:

- EPD identifier;
- EPD digest;
- schema identifier and version;
- composition schema digest;
- source policy digests;
- compiler identity and version;
- compilation time;
- signature identity;
- composition-proof digest;
- active grant identifiers (if any break-glass grants are in effect).

Historical runs MUST retain the exact EPD identity used for authorization.

---

## 16. Core invariant

Adding an ordinary policy contribution MUST NOT increase the set of permitted executions.

Intentional authority expansion requires a separately authorized, bounded, signed grant and remains subject to the non-overridable integrity kernel defined in Section 19.

---

## 17. Review questions

For validation, a reviewer SHOULD answer:

1. Are all policy fields classifiable into one of these semantic types?
2. Are any fields accidentally treated as both permissions and requirements?
3. Is any authority expansion occurring outside signed grants or leases?
4. Can two conforming compilers produce different effective policies?
5. Are all owned fields correctly marked as owned in the schema?
6. Are all cross-field constraints declared in the schema, not in policy sources?
7. Are ranking dimension weights authorized by policy, not computed at runtime?

If the answer to question 4 is yes, the specification still has an ambiguity and MUST be revised before release.

---

## 18. Owned values ("Factory Inventory")

> *Named for the principle that some things in the factory aren't negotiated — they're inventoried by whoever owns them.*

### 18.1 Definition

An **owned value** is a policy field whose effective value is set directly by its authorized owner source, bypassing typed composition. Owned values exist because some fields represent identity or declaration, not constraint — you don't "compose" your organization's name, you declare it.

### 18.2 Schema declaration

The composition schema MUST declare every field as either `composed` or `owned`.

```toml
[schema.fields."/organization/identity"]
type = "string"
mode = "owned"
owner = "organization"
overridable = false

[schema.fields."/project/display_name"]
type = "string"
mode = "owned"
owner = "project"
overridable = false
```

### 18.3 Resolution rules

1. If the owner source provides a value, that value IS the effective value. No composition operator is applied.
2. If a non-owner source provides a value to an owned field, the compiler MUST reject it with UNAUTHORIZED_SOURCE.
3. If `overridable = false` (default), no other source may contribute.
4. If `overridable = true`, lower-precedence sources MAY contribute, and the field composes using its declared operator. The owner's value is treated as one contribution, not a floor.
5. If the owner is absent and the field is required, the compiler MUST produce MISSING_REQUIRED_VALUE.
6. If the owner is absent and a signed schema default exists, the default is used (materialized at stage 9).

### 18.4 Interaction with compilation

Owned values resolve at stage 8, after field-level composition (stage 7). This ordering ensures:
- Composed fields have their effective values ready before cross-field constraints check owned fields against them.
- Schema defaults (stage 9) fill in any absent owned fields that have defaults.

---

## 19. Break-glass protocol ("The Golden Ticket")

> *"A Golden Ticket gets you into the factory. It does not make you the factory owner."*

### 19.1 Purpose

Break-glass provides emergency authority expansion when the effective policy is too restrictive for a critical operation. It is the ONLY mechanism that may increase the set of permitted executions beyond what ordinary composition allows.

### 19.2 Grant structure

A break-glass grant MUST be a signed document containing:

```toml
[grant]
grant_id = "uuid"
issuer = "organization"           # which source class issued it
issuer_identity = "sha256:..."    # identity digest of the issuer
grantee = "run"                   # which source class receives it
grantee_identity = "sha256:..."   # identity digest of the grantee

[grant.scope]
paths = [                          # which policy paths this grant expands
  "/authorization/network_allowed",
  "/authorization/external_writes_allowed"
]
expansion = "permit"              # "permit" or "raise_bound"

[grant.bounds]
max_duration_seconds = 3600       # grant expires after this
max_cost_delta = 100.0            # max additional cost authorized
expires_at = "2026-07-24T00:00:00Z"

[grant.constraints]
integrity_kernel_non_overridable = true   # break-glass CANNOT touch these paths
audit_required = true                     # every action under grant MUST be audited
approval_required = false                 # may be set true for high-risk grants
```

### 19.3 Non-overridable integrity kernel

The following paths are the integrity kernel. Break-glass grants MUST NOT expand, relax, or override them:

- `/integrity/sandbox_required`
- `/integrity/tenant_isolation`
- `/integrity/break_glass_protection`
- `/integrity/audit_required` (under a grant, audit MUST remain on)
- `/verification/policy/required`
- `/data/secrets/exposure_forbidden`

A grant that attempts to scope over any kernel path MUST be rejected as INVALID.

### 19.4 Grant lifecycle

1. **Issuance**: A grant is signed by an authorized issuer. The issuer MUST be a source class with authority over the scoped paths.
2. **Activation**: The grant is presented to the compiler at compilation time. The compiler verifies:
   - signature validity;
   - grantee identity matches the run;
   - `expires_at` is in the future;
   - scoped paths are not in the integrity kernel;
   - grant bounds are within issuer authority.
3. **Effect**: The grant's expansion is applied as an additional contribution at stage 7 (field-level composition), tagged with `source = "grant"` and the `grant_id`.
4. **Expiration**: When `expires_at` passes or `max_duration_seconds` elapses, the grant stops contributing. The compiler MUST produce GRANT_EXPIRED if a grant was previously active and is now expired.
5. **Revocation**: An issuer MAY revoke a grant before expiry. The compiler MUST check a revocation registry at activation. If revoked, the compiler MUST produce GRANT_REVOKED.

### 19.5 Composition interaction

A grant contribution composes using the field's declared operator:

- For a permission boolean (`AND`): the grant contributes `true`, which does not change the result unless the grant is the only source that would otherwise be absent. In practice, grants for permission booleans set the value to `true` directly, overriding the composition.
- For a maximum bound (`min`): the grant may raise the bound up to `max_cost_delta` above the previous effective value, but never above the issuer's own ceiling.
- For an allowlist (`intersection`): the grant MAY add entries to the effective allowlist, but only entries that the issuer's own allowlist already contains.

### 19.6 Audit

Every action authorized under a break-glass grant MUST be logged with:

- grant_id;
- issuer identity;
- grantee identity;
- scoped paths expanded;
- effective values before and after grant;
- timestamp;
- action taken.

Break-glass audit logs MUST be append-only and MUST NOT be deletable by the grantee.

### 19.7 Conformance test additions

In addition to test #10 ("break-glass cannot weaken the integrity kernel"), the conformance suite MUST test:

- A grant signed by an unauthorized issuer is rejected.
- A grant that scopes over a kernel path is rejected.
- An expired grant produces GRANT_EXPIRED.
- A revoked grant produces GRANT_REVOKED.
- A grant cannot raise a maximum bound above the issuer's ceiling.
- A grant cannot add an allowlist entry the issuer doesn't possess.
- Audit logs under a grant are complete and append-only.

---

## 20. Metric registry ("The Measuring Room")

> *Named for the principle that before you can gate on a metric, someone has to define what it means and sign off on it.*

### 20.1 Purpose

The metric registry is a signed, versioned catalog of all metrics that may appear in predicate rules (Section 7.11). It defines metric identifiers, valid units, valid operators, and aggregation methods.

### 20.2 Structure

```toml
[metric."request.error_rate"]
description = "Fraction of requests returning 5xx"
valid_units = ["one", "percent"]
valid_operators = ["gt", "gte", "lt", "lte"]
valid_aggregations = ["rate", "avg", "p99"]
deprecated = false
version = "1.0.0"

[metric."system.cpu_usage"]
description = "CPU utilization fraction"
valid_units = ["one", "percent"]
valid_operators = ["gt", "gte", "lt", "lte"]
valid_aggregations = ["avg", "max"]
deprecated = false
version = "1.0.0"
```

### 20.3 Signing and versioning

The registry MUST be signed. The signature identity MUST be recorded in the composition proof.

Registry versions follow semver. When a metric is deprecated:

- The compiler MUST emit a warning in lint mode.
- The compiler MUST reject the metric in activation mode after the deprecation grace period.
- The deprecation grace period MUST be declared in the registry.

```toml
[registry]
version = "1.3.0"
signer = "sha256:..."
deprecation_grace_days = 90
```

### 20.4 Resolution

At compilation stage 6 (canonicalize), the compiler MUST resolve every predicate metric against the registry. If:

- the metric is unknown → UNKNOWN_SCHEMA_KEY;
- the metric is deprecated and past grace → INVALID;
- the unit is not in `valid_units` → UNIT_CONFLICT;
- the operator is not in `valid_operators` → INVALID;
- the aggregation is not in `valid_aggregations` → INVALID.

The registry version used MUST be recorded in the composition proof.

---

## 21. Schema versioning ("The Recipe Book")

> *Named for the principle that the recipe changes, but every batch is traceable to the recipe version that produced it.*

### 21.1 Schema identity

Every composition schema MUST have:

- schema identifier (URN);
- schema version (semver);
- schema digest (SHA-256 of the canonical serialization);
- signer identity.

### 21.2 Compatibility

Schema versions MUST declare compatibility:

```toml
[schema]
identifier = "urn:agent-control:composition:2.0"
version = "2.1.0"
compatibility = "2.0"   # policy files targeting this compatibility version are accepted
digest = "sha256:..."
```

A policy file declares its target:

```toml
[meta]
schema_compatibility = "2.0"
```

The compiler MUST accept policy files whose `schema_compatibility` matches the schema's declared `compatibility` field. Files targeting an incompatible version MUST be rejected as INVALID.

### 21.3 Adding semantic types

When a new semantic type is added to the schema:

- The schema version MUST be a minor bump (e.g., 2.0 → 2.1).
- Existing policy files that don't use the new type MUST still compile.
- The new type MUST be optional — existing fields MUST NOT be reclassified.

### 21.4 Breaking changes

Breaking changes (removing a type, reclassifying a field, changing an operator) MUST be a major version bump. The compiler MUST reject policy files targeting the old major version.

### 21.5 Migration

The schema MAY include migration declarations:

```toml
[[schema.migrations]]
from = "1.2"
to = "2.0"
transform = "migrate_v1_to_v2"   # references a signed transform function
```

Migration transforms MUST be signed and MUST produce output valid under the target schema version. The compiler MUST record whether a migration was applied in the composition proof.

---

## 22. Performance model ("The Chocolate River")

> *Named for the principle that the river flows fast, but if you fall in, you get pulled out by the Oompa Loompas.*

### 22.1 Caching

The compiled EPD MUST be cacheable. Cache key MUST be:

```
digest(schema) + digest(all_source_policies) + digest(active_grants)
```

If no source policy or grant has changed, the cached EPD MUST be returned without recompilation.

### 22.2 Incremental recomputation

When one source changes, the compiler MAY recompute only the affected fields:

- Fields owned by the changed source → re-resolve.
- Composable fields where the changed source contributed → re-compose.
- Cross-field constraints involving affected fields → re-evaluate.
- Unaffected fields → retain cached effective values.

The incremental result MUST be identical to a full recompilation. The conformance suite MUST verify this invariant.

### 22.3 Latency budget

For the Chocolate Factory Stack (300-agent swarms), the compiler SHOULD target:

- Full compilation: < 100ms for ≤ 50 policy paths.
- Incremental recomputation: < 10ms for single-source changes.
- EPD lookup (cache hit): < 1ms.

These are RECOMMENDED, not REQUIRED. The compiler MUST report actual compilation time in the EPD.

### 22.4 Concurrency

Multiple agents MAY request EPD compilation concurrently. The compiler MUST be thread-safe. Concurrent compilations of the same inputs MUST produce identical EPDs.

---

## 23. Registry-backed constraint providers

The `supports` and `permits` cross-field operators (Section 8.2) require external registries.

### 23.1 Model capability registry

```toml
[registry."kimi-k2.6"]
capabilities = ["code_generation", "tool_use", "vision", "agent_swarm"]
max_context = 131072
```

A `supports` constraint checks whether the effective model's entry contains all required capabilities.

### 23.2 Data classification registry

```toml
[classification."restricted"]
permits_data = ["internal", "confidential", "restricted"]
```

A `permits` constraint checks whether the effective classification permits the data's classification level.

Both registries MUST be signed and versioned, following the same rules as the metric registry (Section 20).

---

## 24. Summary of additions (v2.1)

| Section | Name | What it adds |
| :--- | :--- | :--- |
| 7.12 | Factory Inventory | Owned values definition and resolution |
| 8.1-8.4 | The Contract Room | Cross-field constraint declaration, operators, evaluation |
| 9.2-9.5 | The Tasting Room (expanded) | Ranking dimensions, weight authorization, exploration policy |
| 12 | Result states | Added GRANT_EXPIRED, GRANT_REVOKED |
| 14 | Conformance tests | Added tests 17-20 |
| 15 | EPD identity | Added active grant tracking |
| 18 | Factory Inventory | Full owned values specification |
| 19 | The Golden Ticket | Break-glass grant protocol, integrity kernel, audit |
| 20 | The Measuring Room | Metric registry signing, versioning, deprecation |
| 21 | The Recipe Book | Schema versioning, compatibility, migration |
| 22 | The Chocolate River | EPD caching, incremental recomputation, latency |
| 23 | Registry providers | Model capability and data classification registries |

---

End of specification.
