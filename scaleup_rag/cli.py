import sys
import json
import argparse
from pathlib import Path
from .engine import ScaleUpRAGEngine
from .schemas import RequiredParameterSpec, OperatingEnvelope
from .llm_bridge import live_llm_extractor
from .solver_bridge import run_grounded_simulation

def main():
    parser = argparse.ArgumentParser(description="ScaleUp Read-Through / Write-Back RAG CLI")
    parser.add_argument("--prompt", type=str, help="Natural language simulation prompt")
    parser.add_argument("--entity", type=str, help="Direct parameter entity_name lookup (e.g. dynamic_viscosity)")
    parser.add_argument("--system", type=str, help="Target organism or material (e.g. Saccharina latissima)")
    parser.add_argument("--unit", type=str, default="dimensionless", help="Expected Pint unit (e.g. 'Pa * s')")
    parser.add_argument("--db", type=str, default="sqlite:///scaleup_knowledge.db", help="Database URL")
    parser.add_argument("--simulate", action="store_true", help="Execute end-to-end grounded simulation")
    parser.add_argument("--launch", action="store_true", help="Launch interactive 3D Simulation Workbench in browser")
    parser.add_argument("--port", type=int, default=8000, help="Local server port")
    parser.add_argument("--out", type=str, default=".artifacts/rag_simulation_run.json", help="Path to write simulation artifact")
    args = parser.parse_args()

    engine = ScaleUpRAGEngine(db_url=args.db)

    if args.simulate or args.launch:
        prompt_text = args.prompt or "Simulate E. coli fed-batch fermentation with 500 g/L glucose feed at 37 C"
        result = run_grounded_simulation(
            prompt=prompt_text,
            output_artifact_path=args.out,
            engine=engine,
        )

        audit = result.get("_epistemic_audit", {})
        grounded = audit.get("grounded_parameters", {})
        setpoints = audit.get("user_design_setpoints", {})
        assumptions = audit.get("unverified_assumptions", {})
        gaps = audit.get("parameter_gaps", {})
        summary = result.get("summary", {})

        print("=" * 80)
        print("           ScaleUp RAG Simulation Pipeline Execution Summary            ")
        print("=" * 80)
        print(f"Prompt           : {prompt_text}")
        print(f"Artifact Output  : {args.out}")
        print(f"Run ID           : {result.get('run_id')}")
        print("-" * 80)
        print("EPISTEMIC GROUNDING AUDIT (ZERO HIDDEN CONSTANTS):")
        print(f" 1. Grounded Empirical Parameters ({len(grounded)} verified):")
        for k, v in grounded.items():
            print(f"    * [{k:26s}] = {v['value']} {v['unit']} | DOI: {v['doi']} | Tier: {v['tier']}")

        print(f"\n 2. User Design Setpoints ({len(setpoints)} prompt overrides):")
        for k, v in setpoints.items():
            print(f"    # [{k:26s}] = {v['user_override_value']} {v['unit']} (Literature Baseline: {v['literature_baseline_value']})")

        print(f"\n 3. Unverified Operational Assumptions ({len(assumptions)} explicit hypotheses):")
        for k, v in assumptions.items():
            print(f"    ! [{k:26s}] = {v['fallback_value']} {v['unit']} | Reason: {v['reason']}")

        if gaps:
            print(f"\n 4. Parameter Gaps ({len(gaps)} missing):")
            for k, v in gaps.items():
                print(f"    ? [{k:26s}] = {v['fallback_used']} | Reason: {v['reason']}")

        print("-" * 80)
        print("SOLVER EXECUTION SUMMARY (OXYGEN-COUPLED FED-BATCH):")
        print(f" - Time Steps Simulated : {summary.get('time_steps')} steps ({summary.get('duration_hours')} hours)")
        print(f" - Biomass Trajectory   : {summary.get('initial_biomass_dcw_g_L')} g/L -> {summary.get('final_biomass_dcw_g_L')} g/L")
        print(f" - Volume Trajectory    : {summary.get('initial_volume_L')} L -> {summary.get('final_volume_L')} L")
        print("=" * 80)

        if args.launch:
            from .server import start_server
            # Auto-spawn Godot 4 if present
            try:
                from composition.composition.workflow.skill_research_bridge import _spawn_godot_simulation
                print("Spawning Godot 4 3D simulation scene...")
                _spawn_godot_simulation(str(Path(args.out).resolve()))
            except Exception as ge:
                print(f"Godot spawn info: {ge}")

            print("\nLaunching Interactive 3D Simulation Workbench in Browser...")
            start_server(port=args.port, open_browser=True, block=True)

        return

    if args.entity and args.system:
        spec = RequiredParameterSpec(
            entity_name=args.entity,
            target_system=args.system,
            expected_unit=args.unit,
            envelope_constraints=OperatingEnvelope()
        )
        manifest = engine.resolve_simulation_parameters(
            prompt=f"Direct query for {args.entity} in {args.system}",
            required_specs=[spec],
            llm_extractor_fn=live_llm_extractor
        )
        print(json.dumps(manifest.model_dump(), indent=2))
    elif args.prompt:
        manifest = engine.run_from_prompt(args.prompt)
        print(json.dumps(manifest.model_dump(), indent=2))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
