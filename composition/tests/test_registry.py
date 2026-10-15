"""Tests for the model registry.

Separate from ``test_acceptance.py``: these cover registration and registry
integrity, not the composition criteria CG-01..CG-15.

The properties worth protecting are the conservative ones. Registration is
bookkeeping, so the failure modes are not crashes -- they are a registry that
quietly looks more complete than the repository actually is. These tests are
aimed at that: unknown stays unknown, a digest matches the bytes read, a
reference that does not resolve cannot carry a verdict, and nothing under
``Models/`` is ever written.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

from composition.registry import (
    DIGEST_COVERAGE,
    SCIENTIFIC_STATUS,
    ArtefactDigest,
    IssueKind,
    Origin,
    PortDependence,
    RegisteredModel,
    audit_references,
    build_registry,
    check_references,
    collect_unknowns,
    declared,
    digest_file,
    digest_package,
    register_one,
    summarise_variables,
    unknown,
)

_COMPOSITION_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Built once; registration is a pure function of the files on disk.
_MODELS, _ISSUES = build_registry()

REGISTERED_IDS = sorted(_MODELS)


def _dumps(registry: dict[str, RegisteredModel]) -> str:
    return json.dumps({k: v.to_dict() for k, v in registry.items()}, indent=2)


# --------------------------------------------------------------------------- #
# Every registered model resolves to an existing artefact
# --------------------------------------------------------------------------- #


class TestArtefactsResolve:
    def test_the_registry_is_not_empty(self):
        assert _MODELS, "no model was registered"

    def test_every_model_declares_a_path(self):
        for model in _MODELS.values():
            assert model.specification_path.is_known, model.model_id
            assert model.specification_path.value

    def test_every_declared_path_exists_on_disk(self):
        repo = _COMPOSITION_ROOT.parent
        for model in _MODELS.values():
            target = repo / model.specification_path.value
            assert target.is_dir(), f"{model.model_id}: {target} does not exist"
            assert (target / "pyproject.toml").is_file()

    def test_every_artefact_digest_file_exists(self):
        repo = _COMPOSITION_ROOT.parent
        for model in _MODELS.values():
            assert model.artefact_digests, model.model_id
            for a in model.artefact_digests:
                assert (repo / a.path).is_file(), f"{model.model_id}: {a.path} missing"

    def test_no_issues_on_a_healthy_repository(self):
        assert _ISSUES == [], [i.to_dict() for i in _ISSUES]

    def test_a_missing_package_is_reported_not_substituted(self):
        """Registration must fail loudly rather than reach for another model."""
        from composition.adapters import REGISTRATIONS, AdapterRegistration

        reg = AdapterRegistration(
            model_id="ghost.model",
            model_version="0.0.1",
            factory=lambda w: None,
            model_subdirectory="Models/DoesNotExist",
            worker_module="none",
        )
        model, issues = register_one(reg, base=_COMPOSITION_ROOT.parent)
        assert model is None
        assert [i.kind for i in issues] == [IssueKind.MISSING_ARTEFACT]
        assert "substituted" in issues[0].detail


# --------------------------------------------------------------------------- #
# Digests match the artefacts actually read
# --------------------------------------------------------------------------- #


class TestDigestsMatchArtefacts:
    def test_file_digest_is_sha256_of_the_bytes_on_disk(self):
        repo = _COMPOSITION_ROOT.parent
        for model in _MODELS.values():
            for a in model.artefact_digests:
                data = (repo / a.path).read_bytes()
                assert a.algorithm == "sha256"
                assert a.digest == hashlib.sha256(data).hexdigest(), a.path
                assert a.byte_length == len(data)

    def test_a_tampered_file_would_change_the_digest(self):
        """The digest must actually depend on content, not on the path."""
        import tempfile

        original = bytearray(b"alpha")
        mutated = bytearray(b"bravo")
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "x.py"
            p.write_bytes(bytes(original))
            a = digest_file(p, pathlib.Path(tmp))
            p.write_bytes(bytes(mutated))
            b = digest_file(p, pathlib.Path(tmp))
        assert a.digest != b.digest
        assert a.path == b.path

    def test_package_digest_is_the_documented_function_of_the_file_digests(self):
        for model in _MODELS.values():
            lines = sorted("%s:%s" % (a.path, a.digest) for a in model.artefact_digests)
            expected = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
            assert model.package_digest.value == expected, model.model_id

    def test_package_digest_basis_restates_the_rule(self):
        for model in _MODELS.values():
            assert model.package_digest.origin is Origin.DERIVED
            assert "SHA-256" in model.package_digest.basis

    def test_every_digest_states_what_it_covers(self):
        for model in _MODELS.values():
            assert model.package_digest.basis
            for a in model.artefact_digests:
                assert a.covers, a.path
        assert "SHA-256" in DIGEST_COVERAGE
        assert "excluding" in DIGEST_COVERAGE

    def test_tests_and_caches_are_excluded_from_the_digest_set(self):
        for model in _MODELS.values():
            for a in model.artefact_digests:
                parts = a.path.split("/")
                assert "tests" not in parts, a.path
                assert "__pycache__" not in parts, a.path
                assert not parts[-1].startswith("test_"), a.path

    def test_registration_is_deterministic(self):
        again, _ = build_registry()
        assert _dumps(again) == _dumps(_MODELS)


# --------------------------------------------------------------------------- #
# Unique ids, unambiguous versions
# --------------------------------------------------------------------------- #


class TestIdentityIsUnambiguous:
    def test_every_id_is_unique(self):
        assert len(REGISTERED_IDS) == len(set(REGISTERED_IDS))

    def test_every_model_declares_a_version(self):
        for model in _MODELS.values():
            assert model.model_version, model.model_id

    def test_the_reference_is_id_at_version(self):
        for model in _MODELS.values():
            assert model.reference == "%s@%s" % (model.model_id, model.model_version)

    def test_a_duplicate_id_is_detected(self):
        """Two registrations for one id must be reported, not merged."""
        from composition.registry import builder

        original = builder.REGISTRATIONS
        duplicated = original + (original[0],)
        try:
            builder.REGISTRATIONS = duplicated
            models, issues = builder.build_registry(_COMPOSITION_ROOT.parent)
        finally:
            builder.REGISTRATIONS = original
        kinds = [i.kind for i in issues]
        assert IssueKind.DUPLICATE_ID in kinds
        assert len(models) == len({m.model_id for m in models.values()})

    def test_two_versions_of_one_id_are_flagged_ambiguous(self):
        from composition.registry import builder

        original = builder.REGISTRATIONS
        first = original[0]
        second = type(first)(
            model_id=first.model_id,
            model_version="9.9.9",
            factory=first.factory,
            model_subdirectory=first.model_subdirectory,
            worker_module=first.worker_module,
        )
        try:
            builder.REGISTRATIONS = original + (second,)
            models, issues = builder.build_registry(_COMPOSITION_ROOT.parent)
        finally:
            builder.REGISTRATIONS = original
        ambiguous = [i for i in issues if i.kind is IssueKind.AMBIGUOUS_VERSION]
        assert ambiguous
        assert "bare model_id does not resolve" in ambiguous[0].detail


# --------------------------------------------------------------------------- #
# References to unregistered models
# --------------------------------------------------------------------------- #


class TestReferenceResolution:
    def test_a_registered_reference_resolves(self):
        field = audit_references(REGISTERED_IDS[0], _MODELS)
        assert field.is_known
        assert field.value == "%s@%s" % (REGISTERED_IDS[0],
                                          _MODELS[REGISTERED_IDS[0]].model_version)

    def test_an_unregistered_model_does_not_resolve(self):
        field = audit_references("no.such_model", _MODELS)
        assert not field.is_known
        assert "not in the registry" in field.basis

    def test_a_wrong_version_does_not_resolve(self):
        field = audit_references(REGISTERED_IDS[0], _MODELS, version="99.0.0")
        assert not field.is_known
        assert "ambiguous" in field.basis

    def test_a_matching_version_resolves(self):
        model = _MODELS[REGISTERED_IDS[0]]
        assert audit_references(model.model_id, _MODELS, model.model_version).is_known

    def test_unresolved_references_are_reported(self):
        issues = check_references(
            {"evidence": "ghost.model", "graph": REGISTERED_IDS[0]}, _MODELS)
        assert [i.kind for i in issues] == [IssueKind.UNREGISTERED_REFERENCE]
        assert issues[0].subject == "evidence"

    def test_an_empty_registry_resolves_nothing(self):
        field = audit_references("anything", {})
        assert not field.is_known


# --------------------------------------------------------------------------- #
# Registration is not validation
# --------------------------------------------------------------------------- #


class TestRegistrationIsNotValidation:
    def test_every_model_carries_the_disclaimer(self):
        for model in _MODELS.values():
            assert model.scientific_status["state"] == "registered_only"
            text = " ".join(model.scientific_status.values()).lower()
            assert "does not establish" in text or "does not mean" in text

    def test_the_disclaimer_names_what_is_being_withheld(self):
        assert "correct" in SCIENTIFIC_STATUS[1]
        assert "executable" in SCIENTIFIC_STATUS[1]

    def test_no_registered_model_claims_validation(self):
        for model in _MODELS.values():
            serialised = json.dumps(model.to_dict()).lower()
            for claim in ('"validated": true', '"scientifically_validated"'):
                assert claim not in serialised


# --------------------------------------------------------------------------- #
# Unknown stays unknown
# --------------------------------------------------------------------------- #


class TestUnknownStaysUnknown:
    def test_unknown_helper_is_explicit(self):
        f = unknown("the artefact does not state it")
        assert f.origin is Origin.UNKNOWN
        assert f.value is None
        assert not f.is_known
        assert f.basis

    def test_a_model_with_unknowns_lists_them(self):
        for model in _MODELS.values():
            if model.unknown_fields:
                assert model.unknown_fields == collect_unknowns(model)

    def test_unknowns_are_actually_unknown_on_the_record(self):
        for model in _MODELS.values():
            for name in model.unknown_fields:
                if name == "ports":
                    assert model.port_dependence is PortDependence.INSTANCE
                    continue
                field = getattr(model, name)
                assert field.origin is Origin.UNKNOWN, "%s.%s" % (model.model_id, name)

    def test_morris_publishes_no_doi_and_says_so(self):
        """No DOI is invented from the author or title."""
        morris = _MODELS.get("morris2011.material_balance")
        assert morris is not None
        assert not morris.doi.is_known
        assert "none is inferred" in morris.doi.basis

    def test_an_instance_parameterised_model_does_not_claim_no_ports(self):
        morris = _MODELS["morris2011.material_balance"]
        assert morris.port_dependence is PortDependence.INSTANCE
        assert "ports" in morris.unknown_fields

    def test_zielinski_publishes_its_own_doi(self):
        z = _MODELS["zielinski2019.rhi_process"]
        assert z.doi.is_known
        assert z.doi.value == "10.1016/j.pep.2019.02.002"

    def test_unknowns_carry_a_reason_not_just_a_blank(self):
        for model in _MODELS.values():
            for name in model.unknown_fields:
                if name == "ports":
                    continue
                assert getattr(model, name).basis, "%s.%s" % (model.model_id, name)


# --------------------------------------------------------------------------- #
# Declared content
# --------------------------------------------------------------------------- #


class TestDeclaredContent:
    def test_a_fixed_port_model_records_its_ports(self):
        z = _MODELS["zielinski2019.rhi_process"]
        assert z.port_dependence is PortDependence.FIXED
        assert z.port_counts["input"] + z.port_counts["output"] == len(z.ports)
        assert len(z.ports) == 196

    def test_ports_carry_direction_quantity_and_unit(self):
        for model in _MODELS.values():
            for p in model.ports:
                assert p.port_id and p.direction and p.quantity
                # a port with no declared unit is recorded blank, not guessed
                assert isinstance(p.unit, str)

    def test_variables_and_units_are_derived_from_declared_ports(self):
        z = _MODELS["zielinski2019.rhi_process"]
        assert z.variables.is_known
        assert z.variables.origin is Origin.DECLARED
        assert z.variables.value == summarise_variables(z.ports)

    def test_declared_conditions_come_from_the_artefact(self):
        z = _MODELS["zielinski2019.rhi_process"]
        assert z.required_conditions
        for c in z.required_conditions:
            assert c.condition_id and c.label and c.why_needed

    def test_operating_conditions_are_identified_by_the_models_own_role(self):
        z = _MODELS["zielinski2019.rhi_process"]
        roles = [p.role for p in z.ports if p.role]
        assert "operating_condition" in roles

    def test_summarise_variables_groups_units_by_quantity(self):
        from composition.registry import PortRecord

        ports = (
            PortRecord("a", "input", "Quantity.VOLUME", "mL", False, "", "node:N1"),
            PortRecord("b", "input", "Quantity.VOLUME", "L", False, "", "node:N1"),
            PortRecord("c", "output", "Quantity.TIME", "h", False, "", "node:N1"),
        )
        assert summarise_variables(ports) == {
            "Quantity.TIME": ["h"],
            "Quantity.VOLUME": ["L", "mL"],
        }


# --------------------------------------------------------------------------- #
# The registry is read-only with respect to model artefacts
# --------------------------------------------------------------------------- #


class TestRegistryIsReadOnly:
    def test_no_module_in_the_registry_writes_a_file(self):
        """Read and hash, never write.

        The one exception is the CLI's ``--result`` output, which must live in
        ``__main__.py``'s ``main`` and be guarded by the explicit flag -- the
        same contract ``composition.runner`` and ``composition.evidence`` use.
        """
        import ast

        root = _COMPOSITION_ROOT / "composition" / "registry"
        writers: list[tuple[str, str]] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(
                            node.func, "attr", "") in (
                            "write_text", "write_bytes", "unlink", "rename", "mkdir"):
                        writers.append((path.name, fn.name))
        assert writers == [("__main__.py", "main")] * 2, writers

        source = (root / "__main__.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        guard = next(i for i, line in enumerate(lines, 1)
                     if "if args.result:" in line)
        for call in ("path.parent.mkdir(", "path.write_text("):
            at = next(i for i, line in enumerate(lines, 1) if call in line)
            assert guard < at, f"{call} is not guarded by --result"

    def test_build_registry_does_not_touch_model_packages(self):
        def snapshot(root: pathlib.Path) -> dict[str, tuple[int, float]]:
            out = {}
            for p in sorted(root.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    st = p.stat()
                    out[str(p)] = (st.st_size, st.st_mtime)
            return out

        repo = _COMPOSITION_ROOT.parent
        before = {name: snapshot(repo / name)
                  for name in ("Models",) if (repo / name).is_dir()}
        build_registry()
        after = {name: snapshot(repo / name) for name in before}
        assert before == after

    def test_model_files_are_not_imported_by_the_registry(self):
        """The two model packages collide on a top-level ``models`` name.

        Registration therefore hashes bytes; it never imports a model package.
        """
        import ast

        root = _COMPOSITION_ROOT / "composition" / "registry"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in (
                            "models", "scaleup_ai", "schemas"), alias.name
                elif isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] not in (
                        "models", "scaleup_ai", "schemas"), node.module


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


class TestCli:
    def test_cli_emits_the_registry_and_exits_zero(self):
        out = subprocess.run(
            [sys.executable, "-m", "composition.registry"],
            capture_output=True, text=True, timeout=120,
            cwd=str(_COMPOSITION_ROOT),
        )
        assert out.returncode == 0, out.stderr
        payload = json.loads(out.stdout)
        assert payload["totals"]["models"] == len(_MODELS)
        assert payload["totals"]["issues"] == 0

    def test_cli_result_contract(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "registry.json"
            out = subprocess.run(
                [sys.executable, "-m", "composition.registry", "--result", str(target)],
                capture_output=True, text=True, timeout=120,
                cwd=str(_COMPOSITION_ROOT),
            )
            assert out.returncode == 0, out.stderr
            assert json.loads(out.stdout)["exit_code"] == 0
            assert target.is_file()
            payload = json.loads(target.read_text(encoding="utf-8"))
            assert set(payload["models"]) == set(REGISTERED_IDS)

    def test_cli_payload_carries_the_disclaimer(self):
        out = subprocess.run(
            [sys.executable, "-m", "composition.registry"],
            capture_output=True, text=True, timeout=120,
            cwd=str(_COMPOSITION_ROOT),
        )
        payload = json.loads(out.stdout)
        assert "does NOT establish" in payload["scientific_status"]
        assert "SHA-256" in payload["digest_coverage"]

    def test_cli_output_is_deterministic(self):
        runs = [
            subprocess.run(
                [sys.executable, "-m", "composition.registry"],
                capture_output=True, text=True, timeout=120,
                cwd=str(_COMPOSITION_ROOT),
            ).stdout
            for _ in range(2)
        ]
        assert runs[0] == runs[1]


# --------------------------------------------------------------------------- #
# The evidence catalogue resolves through the registry
# --------------------------------------------------------------------------- #


class TestEvidenceResolvesThroughTheRegistry:
    def test_the_catalogue_names_a_registered_model(self):
        from composition.evidence import REGISTERED_MODEL_ID

        assert REGISTERED_MODEL_ID in _MODELS

    def test_the_record_resolves_to_an_exact_version(self):
        from composition.evidence import ZIELINSKI_RECORD

        assert ZIELINSKI_RECORD.registry_resolution == "resolved"
        assert ZIELINSKI_RECORD.model_reference
        assert ZIELINSKI_RECORD.is_definitive()

    def test_the_record_doi_comes_from_the_artefact(self):
        from composition.evidence import ZIELINSKI_RECORD

        assert ZIELINSKI_RECORD.model_doi == _MODELS["zielinski2019.rhi_process"].doi.value

    def test_the_report_declares_its_verdict_authority(self):
        from composition.evidence import inventory

        assert inventory()["verdict_authority"] == "definitive"

    def test_an_unregistered_model_would_make_the_report_provisional(self):
        """The guard exists even though the catalogue currently resolves."""
        from composition.evidence.conflicts import RecordExamined

        bad = RecordExamined(
            model_id="ghost.model",
            model_source="x",
            model_doi="",
            run_id="r",
            graph_reproducibility_digest="0" * 64,
        )
        assert not bad.is_definitive()