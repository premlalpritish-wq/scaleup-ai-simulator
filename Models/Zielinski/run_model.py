"""CLI: build the model, run both execution modes, write the artifacts.

    python run_model.py [--out DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from models.zielinski_2019 import build_engine  # noqa: E402
from scaleup_ai.report import ModelBundle, write_all  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE / "out"), help="output directory")
    args = ap.parse_args(argv)

    engine = build_engine()
    structural = engine.graph.validate()
    if structural:
        print(f"graph validation produced {len(structural)} message(s):")
        for m in structural:
            print(f"  [{m.severity.value}] {m.code}: {m.message}")
        return 1

    bundle = ModelBundle.build(engine)
    written = write_all(bundle, Path(args.out))

    s = bundle.replay.summary
    print(f"graph      : {engine.graph.graph_id}")
    print(f"nodes      : {len(engine.graph.nodes)}   streams: {len(engine.graph.streams)}")
    print(f"replay     : {s.observed_reference_values} reported, "
          f"{s.digitized_values} digitized, {s.computed_values} computed, "
          f"{s.predicted_values} predicted, {s.unknown_values} unknown")
    print(f"predictive : {bundle.predictive.summary.predicted_values} predictions "
          f"(fails closed without declared inputs)")
    print(f"validation : {s.validation_errors} error(s), {s.validation_warnings} warning(s)")
    print("artifacts  :")
    for name, path in written.items():
        print(f"  {name:16s} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())