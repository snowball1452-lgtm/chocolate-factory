# 🏭 The Chocolate Factory Stack

> A self-hosted, open-source autonomous AI system for play, exploration, and discovery.
> If Willy Wonka built an agent system, this would be it.

## What's Here

### `composition-algebra.md` — The Specification (v2.1.0)
A formal specification for agent-control policy composition using lattice theory.
Defines typed operators (intersection, union, min/max, AND/OR), a 14-stage
compilation pipeline, grants (Golden Ticket break-glass), and the Tasting Room
ranking engine. The taste engine IS the loop engine — it shapes the trajectory
of every agent run through safety gates and exploration policy.

### `compiler/` — The EPD Compiler (84 tests, all passing)
Python implementation of the composition algebra. Compiles policy sources
(organization → environment → project → run) into an Effective Policy Document
(EPD) with full proof trails.

```
compiler/
├── schema.py        # Field definitions, defaults, registries
├── operators.py     # 11 typed composition operators
├── parser.py        # Policy text → structured assignments
├── grants.py        # Golden Ticket grant system
├── compiler.py      # 14-stage compilation pipeline
├── proof.py         # Proof trail data structures
└── tests/           # 84 tests: algebra, conformance, grants, compilation
```

### `adapters/` — Integration Layer (10 tests, all passing)
Connects the compiler to the Chocolate Factory services:

- **Taste Engine** — Eligibility gates + multi-dimensional ranking (novelty,
  exploration_bonus, playfulness, expected_value, cost) with epsilon-greedy /
  Thompson / UCB exploration policies
- **OmniRoute Adapter** — Model routing across 500+ models with fallback chains
- **MeshOS Adapter** — Knowledge graph storage and recall (PostgreSQL + pgvector)
- **SnowDrift Bridge** — Mobile agent (Android) integration
- **Factory Orchestrator** — Ties everything together

### `orchestration/` — Docker Compose Stack (10 services)
One command to spin up the full factory:

```bash
cd orchestration
cp .env.example .env  # Add your API keys
./factory-up.sh        # Start everything
./factory-status.sh    # Health check
```

Services: Ollama, OmniRoute, OpenHands, Crawl4AI, Stirling PDF,
PostgreSQL+pgvector, Hasura, OpenWebUI, Nextcloud, VoxCPM.

### `factory-floor.html` — Live Compiler Demo
Browser-based EPD composition tool with a CRT phosphor aesthetic.
Edit policy sources, compile, and inspect the proof trail in real time.

### `integration_test.py` — Cross-System Tests (7 tests)
Verifies the compiler, taste engine, and grants work together as one system.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   CHOCOLATE FACTORY                       │
│                                                           │
│  RULES    Composition Algebra → EPD Compiler              │
│           (14-stage pipeline, 11 typed operators)         │
│                                                           │
│  TASTE    The Tasting Room → ReAct Loop Engine            │
│           (safety gates fire, then ranking decides)        │
│                                                           │
│  BRAINS   OmniRoute → Ollama / Kimi K2.6 / GPT-5.6 Sol    │
│           (model routing, fallback chains)                │
│                                                           │
│  HANDS    OpenHands, Crawl4AI, Stirling PDF, Browser Use  │
│  MEMORY   MeshOS (PostgreSQL + pgvector + Hasura)         │
│  VOICE    VoxCPM (30 languages, 48kHz)                    │
│  DESKTOP  OpenWebUI, Nextcloud, Odysseus                  │
│  MOBILE   SnowDrift (Android, 29 skills, sovereign mem)   │
└─────────────────────────────────────────────────────────┘
```

## Testing

```bash
cd /path/to/agent-control

# Run all 101 tests
python -m pytest compiler/tests/ adapters/test_adapters.py integration_test.py -v

# Run just the compiler
python -m pytest compiler/tests/ -v

# Run just the adapters
python -m pytest adapters/test_adapters.py -v
```

## License

MIT — Open source. Build your own factory.
