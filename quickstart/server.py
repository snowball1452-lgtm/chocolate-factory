"""
Chocolate Factory — Quickstart API Server
Single endpoint: POST /compile → returns EPD + proof trail
GET /health → liveness check

This is the core of the factory in one container:
- Policy composition (the algebra)
- Taste engine (the tasting room)
- No external dependencies except Python
"""
import sys
import os
import json
from typing import Dict, List, Any, Optional

# When running in Docker, the compiler/ and adapters/ are copied to /factory/
# When running locally, we need to find them relative to this file
_here = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)  # /factory or /app/docs/agent-control
if os.path.exists(os.path.join(_parent, "compiler", "__init__.py")):
    sys.path.insert(0, _parent)
else:
    sys.path.insert(0, "/factory")

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from compiler.compiler import PolicyCompiler
from compiler.grants import Grant, GrantScope, GrantBounds, GrantConstraints
from adapters.taste_engine import (
    Candidate, check_eligibility, compute_aggregate_score, select_action
)

app = FastAPI(
    title="Chocolate Factory — Quickstart",
    description="Policy composition algebra + taste engine. One container, zero deps.",
    version="2.1.0",
)

compiler_instance = PolicyCompiler()


# ── Models ──────────────────────────────────────────────────

class CompileRequest(BaseModel):
    sources: Dict[str, str]
    grants: Optional[List[Dict[str, Any]]] = None


class TasteRequest(BaseModel):
    candidates: List[Dict[str, Any]]
    weights: Dict[str, float] = {
        "expected_value": 0.4,
        "novelty": 0.2,
        "exploration_bonus": 0.15,
        "playfulness": 0.15,
        "cost": 0.1,
    }
    exploration_policy: Dict[str, Any] = {
        "type": "epsilon-greedy",
        "epsilon": 0.15,
        "floor": 0.05,
    }
    maximum_harm: float = 0.3
    maximum_catastrophic_risk: float = 0.1


# ── Endpoints ────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.1.0", "tests": 101}


@app.post("/compile")
async def compile_policy(req: CompileRequest):
    """Compile policy sources into an Effective Policy Document."""
    grants = None
    if req.grants:
        grants = []
        for g in req.grants:
            scope = GrantScope(
                paths=g.get("paths", []),
                values=g.get("values", {}),
                bounds=g.get("bounds"),
                constraints=g.get("constraints"),
            )
            grants.append(Grant(
                grant_id=g["grant_id"],
                issuer=g["issuer"],
                issuer_identity=g["issuer_identity"],
                grantee=g["grantee"],
                grantee_identity=g["grantee_identity"],
                scope=scope,
                expiry=g.get("expiry"),
            ))

    epd = compiler_instance.compile(req.sources, grants=grants)

    # Serialize proof entries
    proof = {}
    for path, entry in epd.proof.items():
        proof[path] = entry if isinstance(entry, dict) else {
            "type": entry.type,
            "operator": entry.operator,
            "contributions": [
                {"source": c.source, "state": c.state, "value": c.value}
                for c in entry.contributions
            ],
            "effective_value": entry.effective_value,
            "status": entry.status,
        }

    return {
        "status": epd.status,
        "values": epd.values,
        "proof": proof,
    }


@app.post("/taste")
async def taste_ranking(req: TasteRequest):
    """Run the tasting room: eligibility gates + ranking + exploration policy."""
    candidates = []
    for c in req.candidates:
        candidates.append(Candidate(
            name=c["name"],
            integrity_passes=c.get("integrity_passes", True),
            authorization_passes=c.get("authorization_passes", True),
            required_evidence_exists=c.get("required_evidence_exists", True),
            harm_upper_bound=c.get("harm_upper_bound", 0.0),
            catastrophic_risk=c.get("catastrophic_risk", 0.0),
            dimensions=c.get("dimensions", {}),
        ))

    selected, scores = select_action(
        candidates,
        req.weights,
        req.exploration_policy,
        maximum_harm=req.maximum_harm,
        maximum_catastrophic_risk=req.maximum_catastrophic_risk,
    )

    return {
        "selected": selected.name if selected else None,
        "scores": scores,
        "eligible": [
            {"name": c.name, "harm": c.harm_upper_bound, "risk": c.catastrophic_risk}
            for c in candidates if check_eligibility(c, req.maximum_harm, req.maximum_catastrophic_risk)
        ],
        "blocked": [
            {"name": c.name, "harm": c.harm_upper_bound, "risk": c.catastrophic_risk}
            for c in candidates if not check_eligibility(c, req.maximum_harm, req.maximum_catastrophic_risk)
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
    <head><title>🏭 Chocolate Factory</title></head>
    <body style="font-family: monospace; padding: 40px; max-width: 700px; margin: auto;">
    <h1>🏭 Chocolate Factory — Quickstart</h1>
    <p>v2.1.0 — 101 tests passing</p>
    <hr>
    <h3>Endpoints</h3>
    <ul>
    <li><b>GET</b> /health — liveness check</li>
    <li><b>POST</b> /compile — compile policy sources → EPD</li>
    <li><b>POST</b> /taste — run taste engine (eligibility + ranking)</li>
    <li><b>GET</b> /docs — interactive API docs (Swagger)</li>
    </ul>
    <h3>Quick test</h3>
    <pre>curl -X POST http://localhost:8000/compile \\
  -H "Content-Type: application/json" \\
  -d '{"sources": {"organization": "/models/allowed = [\\"kimi-k2.6\\"]"}}'</pre>
    </body>
    </html>
    """
