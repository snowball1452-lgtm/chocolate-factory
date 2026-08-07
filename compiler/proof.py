# docs/agent-control/compiler/proof.py

from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

@dataclass
class ContributionProof:
    source: str  # organization, environment, project, run, grant
    state: str   # explicit, absent
    value: Any = None
    digest: Optional[str] = None

@dataclass
class ProofEntry:
    path: str
    type: str
    operator: str
    contributions: List[ContributionProof] = field(default_factory=list)
    effective_value: Any = None
    status: str = "SATISFIED"  # SATISFIED, DENIED, UNSATISFIABLE, etc.
    source_digests: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "path": self.path,
            "type": self.type,
            "operator": self.operator,
            "contributions": [],
            "effective_value": self.effective_value,
            "status": self.status
        }
        for c in self.contributions:
            cd = {
                "source": c.source,
                "state": c.state
            }
            if c.state == "explicit":
                cd["value"] = c.value
            if c.digest:
                cd["digest"] = c.digest
            res["contributions"].append(cd)
        return res

@dataclass
class EPDIdentity:
    epd_id: str
    epd_digest: str
    schema_identifier: str
    schema_version: str
    composition_schema_digest: str
    source_policy_digests: Dict[str, str]
    compiler_identity: str = "agent-control-compiler/py"
    compiler_version: str = "2.1.0"
    compilation_time: str = ""
    signature_identity: str = "sha256:default_compiler_signature"
    composition_proof_digest: str = ""
    active_grants: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epd_id": self.epd_id,
            "epd_digest": self.epd_digest,
            "schema_identifier": self.schema_identifier,
            "schema_version": self.schema_version,
            "composition_schema_digest": self.composition_schema_digest,
            "source_policy_digests": self.source_policy_digests,
            "compiler_identity": self.compiler_identity,
            "compiler_version": self.compiler_version,
            "compilation_time": self.compilation_time,
            "signature_identity": self.signature_identity,
            "composition_proof_digest": self.composition_proof_digest,
            "active_grants": self.active_grants
        }
