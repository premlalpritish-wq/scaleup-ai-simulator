#!/usr/bin/env python3
"""Unified tool: Fill knowledge gaps once, cache in central_library.json, and launch Godot.

Usage:
    python composition/tools/research_to_godot.py --prompt "<prompt>" --auto-research --launch-godot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add composition package root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
COMPOSITION_ROOT = REPO_ROOT / "composition"
if str(COMPOSITION_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPOSITION_ROOT))

from composition.workflow.skill_research_bridge import resolve_prompt_and_research


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill knowledge gaps via open-source skills, update central_library.json, and launch Godot.",
    )
    parser.add_argument("--prompt", required=True, help="Bioprocess simulation prompt")
    parser.add_argument(
        "--auto-research",
        action="store_true",
        default=True,
        help="Fetch missing literature via OpenAlex/CrossRef when gaps exist (default: True)",
    )
    parser.add_argument(
        "--no-auto-research",
        action="store_false",
        dest="auto_research",
        help="Do not query external literature search APIs",
    )
    parser.add_argument(
        "--launch-godot",
        action="store_true",
        help="Spawn Godot simulation scene immediately",
    )
    parser.add_argument(
        "--result",
        help="Optional path to write output JSON",
    )

    args = parser.parse_args()

    payload, code = resolve_prompt_and_research(
        prompt_text=args.prompt,
        auto_research=args.auto_research,
        launch_godot=args.launch_godot,
        base=REPO_ROOT,
    )

    print(f"Reconstruction status: {payload.get('status')}")
    print(f"Cache hit: {payload.get('cache_hit')}")
    summary = payload.get("summary", {})
    print(f"Combined papers: {summary.get('combined_paper_count')}")
    print(f"Cross-paper connections: {summary.get('cross_paper_connection_count')}")
    print(f"Diagram: {payload.get('diagram_path')}")
    print(f"Run artifact saved to: .artifacts/latest_prompt_run.json")

    return code


if __name__ == "__main__":
    sys.exit(main())
