"""The manifest, and the committed copy of it.

`manifest.json` is a snapshot of what `baez2014.manifest.build_manifest()`
declares. `tests/test_manifest.py` fails if the two ever differ, so the file
cannot quietly go stale, and `python -m baez2014 --check manifest.json` is the
same comparison from the command line.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _baez_testkit import MANIFEST_PATH, PACKAGE_ROOT as ROOT

from baez2014 import manifest as manifest_module
from baez2014.manifest import ARTEFACT_ID, VERSION, build_manifest


def test_committed_manifest_matches_what_the_package_declares() -> None:
    assert MANIFEST_PATH.is_file(), "manifest.json is missing"
    committed = MANIFEST_PATH.read_text(encoding="utf-8")
    rendered = json.dumps(
        build_manifest(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    assert committed == rendered, (
        "manifest.json is stale; regenerate with "
        "'python -m baez2014 > manifest.json' from the Baez directory"
    )


def test_cli_check_accepts_the_committed_manifest() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "baez2014", "--check", "manifest.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_cli_check_rejects_a_tampered_copy(tmp_path: Path) -> None:
    tampered = tmp_path / "manifest.json"
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["version"] = "9.9.9"
    tampered.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "baez2014", "--check", str(tampered)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "differs from the manifest this package declares" in result.stderr


def test_cli_check_reports_a_missing_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "baez2014", "--check", str(tmp_path / "absent.json")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "no such file" in result.stderr


def test_cli_writes_the_manifest_to_stdout_only() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "baez2014"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["artefact_id"] == ARTEFACT_ID
    assert payload["version"] == VERSION


# --------------------------------------------------------------------------- #
# what the manifest claims
# --------------------------------------------------------------------------- #


def test_manifest_declares_one_equation_and_six_observations() -> None:
    document = build_manifest()
    assert len(document["equations"]) == 1
    assert document["equations"][0]["equation_id"] == "source_formula.exponential_feed_rate"
    assert len(document["observations"]) == 6
    assert len(document["missing_models"]) == 7
    assert len(document["experimental_conditions"]) == 10


def test_manifest_records_the_four_required_run_inputs_and_no_defaults() -> None:
    required = build_manifest()["required_run_inputs"]
    assert [entry["name"] for entry in required] == ["X_F", "V_F", "t_F", "t"]
    for entry in required:
        assert entry["defaulted"] is False
        assert entry["definition_as_printed"]
        assert entry["unit"]


def test_manifest_records_the_four_reported_parameters_with_their_pages() -> None:
    parameters = build_manifest()["reported_parameters"]
    assert set(parameters) == {"mu_set", "Y_XS", "m", "S_F"}
    for name, entry in parameters.items():
        assert entry["provenance"] == "reported", name
        assert entry["basis"] == "observed_reference", name
        assert entry["evidence"][0]["printed_page"] == 6, name
        assert entry["method"] is None, name


def test_manifest_cites_the_source_and_does_not_invent_metadata() -> None:
    src = build_manifest()["source"]
    assert src["doi"] == "10.1186/1475-2859-13-50"
    assert src["printed_pages"] == [1, 7]
    assert src["printed_page_equals_pdf_page"] is True
    assert "Page 2 of 7" in src["page_numbering_evidence"]
    assert "page 1 carries the journal line" in src["page_numbering_evidence"]
    assert set(src) == {
        "source_id", "authors", "title", "journal", "year", "volume",
        "article_number", "pages", "doi", "citation", "printed_pages",
        "printed_page_equals_pdf_page", "page_numbering_evidence",
    }


def test_manifest_carries_the_disclaimer() -> None:
    disclaimer = build_manifest()["disclaimer"]
    assert "does not establish scientific validity" in disclaimer


def test_manifest_is_deterministic() -> None:
    assert json.dumps(build_manifest(), sort_keys=True) == json.dumps(
        build_manifest(), sort_keys=True
    )
    assert manifest_module.ARTEFACT_ID == "baez2014-oxygen-induced"
    assert manifest_module.VERSION == "0.1.0"


def test_manifest_version_matches_pyproject() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{VERSION}"' in text
    assert f'name = "{ARTEFACT_ID}"' in text