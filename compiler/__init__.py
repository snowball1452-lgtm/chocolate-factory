# docs/agent-control/compiler/__init__.py

from compiler.schema import Schema, SchemaField, CrossFieldConstraint
from compiler.parser import parse_policy_file, parse_policy_text
from compiler.operators import compose_values, is_less_permissive_or_equal, ABSENT
from compiler.grants import Grant, verify_and_activate_grant
from compiler.compiler import PolicyCompiler, EffectivePolicyDocument
from compiler.proof import ProofEntry, ContributionProof
