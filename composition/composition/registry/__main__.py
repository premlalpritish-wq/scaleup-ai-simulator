"""Emit the model registry as JSON.

Takes the same ``--result <path>`` contract as ``composition.runner`` and
``composition.evidence``, so downstream tools read every artefact the same way.

The registry is built by reading and hashing model files. Nothing is written
to a model package.
"""

from __future__ import annotations

import json
import sys


def report() -> dict:
    from .builder import DIGEST_COVERAGE, build_registry, check_references

    models, issues = build_registry()
    payload = {
        "registry_version": "1",
        "digest_coverage": DIGEST_COVERAGE,
        "scientific_status": (
            "Registration records that a specification artefact exists, is "
            "identified, and can be located and hashed. It does NOT establish "
            "that a model is correct, independently supported, or executable."
        ),
        "models": {mid: m.to_dict() for mid, m in sorted(models.items())},
        "issues": [i.to_dict() for i in issues],
        "totals": {
            "models": len(models),
            "artefacts": sum(len(m.artefact_digests) for m in models.values()),
            "ports": sum(len(m.ports) for m in models.values()),
            "issues": len(issues),
            "models_with_unknown_fields": sum(
                1 for m in models.values() if m.unknown_fields
            ),
        },
    }

    # Anything elsewhere in the repository that names a model must resolve.
    references = {}
    try:
        from ..evidence.catalogue import REGISTERED_MODEL_ID

        references["evidence.catalogue"] = REGISTERED_MODEL_ID
    except Exception:                                          # noqa: BLE001
        pass
    payload["references"] = {
        "checked": references,
        "unresolved": [i.to_dict() for i in check_references(references, models)],
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="python -m composition.registry",
        description="Report the deterministic model registry.",
    )
    parser.add_argument("--result", help="path to write the registry JSON")
    args = parser.parse_args(argv)

    payload = report()
    text = json.dumps(payload, indent=2) + "\n"
    if args.result:
        path = Path(args.result)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        json.dump(
            {
                "registry_file": str(path),
                "models": payload["totals"]["models"],
                "artefacts": payload["totals"]["artefacts"],
                "issues": payload["totals"]["issues"],
                "exit_code": 0 if payload["totals"]["issues"] == 0 else 2,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text)
    # A registry that found a problem should not exit zero.
    return 0 if payload["totals"]["issues"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())