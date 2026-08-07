# docs/agent-control/adapters/factory_orchestrator.py

import sys
import os
import argparse
import json
from typing import List, Dict, Any, Tuple, Optional, Union

# Add the compiler directory and current directory to sys.path to enable imports
compiler_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "compiler"))
if compiler_path not in sys.path:
    sys.path.append(compiler_path)

adapters_path = os.path.abspath(os.path.dirname(__file__))
if adapters_path not in sys.path:
    sys.path.append(adapters_path)

import schema as compiler_schema
import operators as compiler_operators

# Import adapters and taste engine directly
from taste_engine import (
    Candidate, select_action, compose_weights, check_eligibility
)
from omniroute_adapter import OmniRouteAdapter
from meshos_adapter import MeshOSAdapter
from snowdrift_bridge import SnowDriftBridge


class PolicyCompiler:
    """
    Compiler that merges policy files/sources using composition-algebra.md rules.
    """
    def __init__(self):
        self.schema = compiler_schema.Schema()
        
        # Dynamically register taste-engine schema fields if they aren't registered
        # Weights (numerical, highest wins, i.e., min_bound since in operators min_bound uses max)
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/expected_value", "min_bound", default=0.0))
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/novelty", "min_bound", default=0.0))
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/exploration_bonus", "min_bound", default=0.0))
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/playfulness", "min_bound", default=0.0))
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/cost", "min_bound", default=0.0))
        self.schema.add_field(compiler_schema.SchemaField("/taste/weights/harm_upper_bound", "min_bound", default=0.0))
        
        # Exploration parameters
        self.schema.add_field(compiler_schema.SchemaField("/taste/exploration/strategy", "ordered_floor", default="epsilon-greedy"))
        self.schema.add_field(compiler_schema.SchemaField("/taste/exploration/epsilon", "min_bound", default=0.15))
        self.schema.add_field(compiler_schema.SchemaField("/taste/exploration/annealing", "ordered_floor", default="none"))
        self.schema.add_field(compiler_schema.SchemaField("/taste/exploration/floor", "min_bound", default=0.05))

    def compile(self, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compiles multiple policy sources into an Effective Policy Document (EPD).
        sources is a list of dicts: [{"source": "organization", "values": {...}}, ...]
        """
        # Stage 7: Field-level typed composition
        field_values = {path: compiler_operators.ABSENT for path in self.schema.fields}

        for path, field in self.schema.fields.items():
            if field.mode == "owned":
                continue
                
            current_val = compiler_operators.ABSENT
            for src in sources:
                src_val = src.get("values", {}).get(path, compiler_operators.ABSENT)
                if src_val is not compiler_operators.ABSENT:
                    current_val = compiler_operators.compose_values(field.type, current_val, src_val)
                    
            field_values[path] = current_val

        # Stage 8: Resolve owned values
        for path, field in self.schema.fields.items():
            if field.mode == "owned":
                owner_src_class = field.owner
                owning_val = compiler_operators.ABSENT
                
                for src in sources:
                    src_class = src.get("source")
                    src_val = src.get("values", {}).get(path, compiler_operators.ABSENT)
                    if src_val is not compiler_operators.ABSENT:
                        if src_class != owner_src_class:
                            raise ValueError(f"UNAUTHORIZED_SOURCE: Source '{src_class}' cannot set owned field '{path}' (owned by '{owner_src_class}')")
                        else:
                            owning_val = src_val
                
                field_values[path] = owning_val

        # Stage 9: Materialize defaults
        for path, field in self.schema.fields.items():
            if field_values[path] is compiler_operators.ABSENT:
                if field.required:
                    raise ValueError(f"MISSING_REQUIRED_VALUE: Required field '{path}' is absent and has no default.")
                field_values[path] = field.default

        # Stage 10: Evaluate cross-field constraints
        for constraint in self.schema.constraints:
            left_val = field_values.get(constraint.left)
            right_val = field_values.get(constraint.right)
            
            if left_val is compiler_operators.ABSENT or right_val is compiler_operators.ABSENT:
                continue
                
            satisfied = self._evaluate_constraint(constraint.operator, left_val, right_val)
            if not satisfied:
                raise ValueError(f"UNSATISFIABLE: Constraint '{constraint.id}' violated: left '{constraint.left}' ({left_val}) {constraint.operator} right '{constraint.right}' ({right_val}) is false.")

        # Construct final EPD
        epd = {}
        for path, val in field_values.items():
            if val is compiler_operators.ABSENT:
                epd[path] = None
            else:
                epd[path] = val
                
        return epd

    def _evaluate_constraint(self, op: str, left: Any, right: Any) -> bool:
        if op == "le":
            return left <= right
        elif op == "lt":
            return left < right
        elif op == "ge":
            return left >= right
        elif op == "gt":
            return left > right
        elif op == "eq":
            return left == right
        elif op == "ne":
            return left != right
        elif op == "subseteq":
            return set(left).issubset(set(right))
        elif op == "supports":
            model_info = compiler_schema.DEFAULT_MODEL_CAPABILITY_REGISTRY.get(left)
            if not model_info:
                return False
            capabilities = model_info.get("capabilities", [])
            if isinstance(right, list):
                return all(cap in capabilities for cap in right)
            return right in capabilities
        elif op == "permits":
            left_info = compiler_schema.DEFAULT_DATA_CLASSIFICATION_REGISTRY.get(left)
            if not left_info:
                return False
            permitted = left_info.get("permits_data", [])
            if isinstance(right, list):
                return all(d in permitted for d in right)
            return right in permitted
        else:
            return False


class FactoryOrchestrator:
    """
    Top-level orchestrator for the Chocolate Factory Stack.
    Ties together compilation, OmniRoute LLM calls, MeshOS memory graph,
    the taste engine selection loop, and SnowDrift mobile delegation.
    """
    def __init__(
        self,
        omniroute_url: str = "http://localhost:18789",
        meshos_url: str = "http://localhost:8080/v1/graphql",
        snowdrift_url: str = "http://localhost:8000"
    ):
        self.compiler = PolicyCompiler()
        self.omniroute = OmniRouteAdapter(omniroute_url)
        self.meshos = MeshOSAdapter(meshos_url)
        self.snowdrift = SnowDriftBridge(snowdrift_url)
        
        # Cache compiled EPD for convenience
        self.latest_epd: Optional[Dict[str, Any]] = None

    def compile_policy(self, sources: List[Dict[str, Any]], agent_id: str) -> Dict[str, Any]:
        """
        Compiles the policy sources, stores the EPD to MeshOS, pushes to SnowDrift, and caches locally.
        """
        epd = self.compiler.compile(sources)
        self.latest_epd = epd
        
        # Store in MeshOS memory graph
        try:
            self.meshos.store_epd(epd, agent_id)
        except Exception as e:
            print(f"[Warning] Failed to store EPD in MeshOS: {e}")
            
        # Push to SnowDrift mobile device
        try:
            self.snowdrift.push_policy_epd(agent_id, epd)
        except Exception as e:
            print(f"[Warning] Failed to push EPD to SnowDrift: {e}")
            
        return epd

    def execute_loop_iteration(
        self,
        agent_id: str,
        candidates: List[Union[Candidate, Dict[str, Any]]],
        prompt: str,
        step: int = 0
    ) -> Tuple[Optional[Union[Candidate, Dict[str, Any]]], Dict[str, Any]]:
        """
        Runs one step of the ReAct taste loop:
        1. Composes/extracts weights and exploration parameters from latest compiled EPD.
        2. Applies taste engine safety gates and ranking to choose the best eligible candidate.
        3. If task is chosen and is flagged as a mobile task, delegates it to SnowDrift.
        4. Saves interaction memories and states to MeshOS memory graph.
        5. Synchronizes mobile memories.
        """
        # Ensure we have compiled policy weights
        if not self.latest_epd:
            # Fallback to schema defaults
            self.latest_epd = self.compiler.compile([])
            
        # Extract weights from latest compiled EPD
        weights = {
            "expected_value": self.latest_epd.get("/taste/weights/expected_value", 0.0),
            "novelty": self.latest_epd.get("/taste/weights/novelty", 0.0),
            "exploration_bonus": self.latest_epd.get("/taste/weights/exploration_bonus", 0.0),
            "playfulness": self.latest_epd.get("/taste/weights/playfulness", 0.0),
            "cost": self.latest_epd.get("/taste/weights/cost", 0.0),
            "harm_upper_bound": self.latest_epd.get("/taste/weights/harm_upper_bound", 0.0)
        }
        
        # Extract exploration policy from latest compiled EPD
        exploration_policy = {
            "strategy": self.latest_epd.get("/taste/exploration/strategy", "epsilon-greedy"),
            "epsilon": self.latest_epd.get("/taste/exploration/epsilon", 0.15),
            "annealing": self.latest_epd.get("/taste/exploration/annealing", "none"),
            "floor": self.latest_epd.get("/taste/exploration/floor", 0.05)
        }
        
        # Run Taste Engine decision loop
        selected_candidate, score_details = select_action(
            candidates=candidates,
            weights=weights,
            exploration_policy=exploration_policy,
            step=step,
            maximum_harm=self.latest_epd.get("/run/maximum_cost", 0.5), # maps to safety limit or default
            maximum_catastrophic_risk=0.5
        )
        
        execution_metadata = {
            "step": step,
            "weights_used": weights,
            "exploration_policy_used": exploration_policy,
            "all_scored_candidates": score_details
        }
        
        if not selected_candidate:
            print("[Orchestrator] No eligible candidates passed the taste engine gates!")
            return None, execution_metadata
            
        selected_name = (
            selected_candidate.name if isinstance(selected_candidate, Candidate)
            else selected_candidate.get("name", "unknown")
        )
        selected_metadata = (
            selected_candidate.metadata if isinstance(selected_candidate, Candidate)
            else selected_candidate.get("metadata", {})
        )
        
        # Store selection decision memory in MeshOS
        try:
            mem_id = self.meshos.store_memory(
                content=f"ReAct Loop Step {step}: Selected action '{selected_name}' based on taste engine ranking.",
                agent_id=agent_id,
                memory_type="react_decision",
                metadata={"prompt": prompt, "selection_scores": score_details}
            )
            execution_metadata["decision_memory_id"] = mem_id
        except Exception as e:
            print(f"[Warning] Failed to store decision memory in MeshOS: {e}")
            
        # Delegate to SnowDrift if the candidate is marked as mobile
        if selected_metadata.get("destination") == "mobile":
            print(f"[Orchestrator] Delegating action '{selected_name}' to mobile (SnowDrift)...")
            try:
                task_payload = {
                    "action_name": selected_name,
                    "metadata": selected_metadata
                }
                task_res = self.snowdrift.send_task_to_mobile(agent_id, task_payload)
                execution_metadata["mobile_task_result"] = task_res
                
                # Fetch result back
                task_id = task_res.get("task_id")
                if task_id:
                    result_res = self.snowdrift.receive_mobile_result(task_id)
                    execution_metadata["mobile_task_output"] = result_res
            except Exception as e:
                print(f"[Warning] SnowDrift task delegation failed: {e}")
                
        # Synchronize memory with mobile
        try:
            self.snowdrift.sync_memory(agent_id)
        except Exception as e:
            print(f"[Warning] Failed to sync memory with SnowDrift: {e}")
            
        return selected_candidate, execution_metadata


def main():
    parser = argparse.ArgumentParser(description="Chocolate Factory Stack - Orchestrator CLI")
    parser.add_argument("--agent-id", type=str, default="agent_007", help="Agent unique ID")
    parser.add_argument("--compile-only", action="store_true", help="Only compile the specified policy sources")
    parser.add_argument("--sources-json", type=str, help="Path to policy sources JSON file")
    
    args = parser.parse_args()
    
    orchestrator = FactoryOrchestrator()
    
    # Load sources
    sources = []
    if args.sources_json and os.path.exists(args.sources_json):
        try:
            with open(args.sources_json, 'r') as f:
                sources = json.load(f)
        except Exception as e:
            print(f"Error reading sources json: {e}")
            sys.exit(1)
    else:
        # Default mock sources
        sources = [
            {
                "source": "organization",
                "values": {
                    "/integrity/sandbox_required": True,
                    "/taste/weights/expected_value": 0.5,
                    "/taste/weights/novelty": 0.2,
                    "/taste/weights/exploration_bonus": 0.3,
                    "/taste/exploration/strategy": "epsilon-greedy",
                    "/taste/exploration/epsilon": 0.2
                }
            }
        ]
        
    print(f"Compiling policy sources for Agent ID: {args.agent_id}...")
    try:
        epd = orchestrator.compile_policy(sources, args.agent_id)
        print("Effective Policy Document (EPD) Compiled successfully:")
        print(json.dumps(epd, indent=2))
    except Exception as e:
        print(f"Policy compilation failed: {e}")
        sys.exit(1)
        
    if args.compile_only:
        return
        
    # Mock Candidates
    candidates = [
        Candidate(
            name="Run local database migration check",
            integrity_passes=True,
            authorization_passes=True,
            required_evidence_exists=True,
            harm_upper_bound=0.1,
            catastrophic_risk=0.05,
            dimensions={"expected_value": 0.8, "novelty": 0.1, "exploration_bonus": 0.2, "cost": 0.05}
        ),
        Candidate(
            name="Deploy staging build to cloud environment",
            integrity_passes=True,
            authorization_passes=False, # Auth fails!
            required_evidence_exists=True,
            harm_upper_bound=0.2,
            catastrophic_risk=0.1,
            dimensions={"expected_value": 0.95, "novelty": 0.5, "exploration_bonus": 0.4, "cost": 1.5}
        ),
        Candidate(
            name="Ping mobile location service daemon",
            integrity_passes=True,
            authorization_passes=True,
            required_evidence_exists=True,
            harm_upper_bound=0.05,
            catastrophic_risk=0.01,
            dimensions={"expected_value": 0.6, "novelty": 0.9, "exploration_bonus": 0.8, "cost": 0.1},
            metadata={"destination": "mobile", "service": "location"}
        )
    ]
    
    print("\nRunning a ReAct loop step selection over 3 candidate actions...")
    selected, details = orchestrator.execute_loop_iteration(
        agent_id=args.agent_id,
        candidates=candidates,
        prompt="Synthesize latest metrics and perform system diagnostics.",
        step=1
    )
    
    if selected:
        print(f"\nSUCCESS! Selected Action: '{selected.name}'")
        print("Details:")
        print(json.dumps(details, indent=2))
    else:
        print("\nDecision failed: No candidates passed eligibility gates.")


if __name__ == "__main__":
    main()
