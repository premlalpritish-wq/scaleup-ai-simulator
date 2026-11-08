"""Tests for the research explorer: the browser page and the boundary behind it.

Two layers are covered:

* the Python adapter (`api/research.py`) against the shipped pecan artifacts and
  the real workflow -- including the refusals, the quote re-verification and the
  promise that analogous evidence is never served as direct evidence;
* the HTTP surface (`api/app.py`) served by a real `BoundedThreadingHTTPServer` on
  an ephemeral port -- the page, the case, an analysis, a refusal, feedback,
  artifact downloads and path traversal.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
import app  # noqa: E402
import research  # noqa: E402


# --------------------------------------------------------------- the adapter

def test_case_is_the_shipped_run_and_every_quote_is_rechecked() -> None:
    case = research.load_case()
    assert case["origin"] == "composition/workflow_runs/pecan"
    summary = case["summary"]
    assert summary["claim_count"] == 25
    assert summary["direct_claims"] == 6
    assert summary["analogue_claims"] == 17
    assert summary["method_review_claims"] == 2
    assert summary["step_count"] == 18
    assert summary["source_count"] == 5
    assert summary["protocol_complete_for_target"] is False
    assert summary["quantitative_yield_available_for_target"] is False
    recheck = case["verification"]["quote_recheck"]
    assert recheck["checked"] == 25
    assert recheck["failed"] == 0
    assert case["verification"]["source_role_check"] == "enforced"


def test_direct_evidence_only_ever_comes_from_the_pecan_paper() -> None:
    case = research.load_case()
    for claim in case["claims"]:
        assert claim["source"]["source_id"]
        assert claim["source"]["title"]
        assert claim["source"]["doi"]
        assert claim["quote"]
        if claim["evidence_class"] == "direct":
            assert claim["source"]["role"] == "target_organism"
            assert claim["source"]["source_id"] == "pecan_miRNome"
            assert claim["hypothesis"] is False
        elif claim["evidence_class"] == "analogue":
            assert claim["source"]["role"] == "analogous_protocol"
            assert claim["source"]["source_id"] != "pecan_miRNome"
            assert claim["hypothesis"] is True
        else:
            assert claim["source"]["role"] == "method_review"
            assert claim["source"]["source_id"] != "pecan_miRNome"


def test_gaps_name_every_unknown_and_offer_no_recommendation() -> None:
    case = research.load_case()
    gaps = case["gaps"]
    assert len(gaps) == 44
    unresolved = [gap for gap in gaps if gap["class"] == "unresolved_parameter"]
    assert len(unresolved) == case["summary"]["unresolved_parameter_count"] == 18
    for gap in gaps:
        assert gap["state"] == "unknown"
        assert gap["why"]
        assert "should" not in gap["why"].lower()
        for reference in gap["hypothesis_references"]:
            assert reference["evidence_status"].startswith("analogous")
            assert reference["value"] is not None


def test_a_tampered_artifact_stops_the_case_instead_of_serving_evidence(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = scratch / "case"
    shutil.copytree(research.CASE_RUN_DIR, copy)
    result_file = copy / "workflow_result.json"
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    payload["encoded"]["claims"][0]["quote"] = "A sentence that is not in the paper."
    result_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(research, "CASE_RUN_DIR", copy)
    with pytest.raises(research.ResearchError) as exc:
        research.load_case()
    assert exc.value.code == "case_unverified"
    assert exc.value.status == 503


def test_analysis_runs_the_real_workflow_and_returns_computed_outputs() -> None:
    payload, status = research.analyse(
        {
            "problem": (
                "Extract high-quality total RNA from pecan (Carya illinoinensis) "
                "embryos for small RNA sequencing."
            ),
            "organism": "Carya illinoinensis",
            "tissue": "embryo",
            "molecule": "total RNA",
            "extraction_method": "TRIzol kit",
            "observations": "brown pellet after precipitation",
        }
    )
    assert status == 200
    assert payload["status"] == "completed"
    assert payload["applicability"]["applicable"] is True
    result = payload["result"]
    outputs = {item["port_id"]: item["value"] for item in result["execution"]["outputs"]}
    assert outputs["claim_count"] == 25.0
    assert outputs["direct_target_claim_count"] == 6.0
    assert outputs["analogue_claim_count"] == 17.0
    assert outputs["unresolved_parameter_count"] == 18.0
    assert outputs["quantitative_yield_available_for_target"] == 0.0
    for forbidden in ("predicted_yield", "degradation_rate", "yield_ug", "rin"):
        assert forbidden not in outputs
    # The two kinds of input are reported separately, and the recorded one is
    # never claimed to be evidence.
    assert payload["input"]["used"]["organism"] == "Carya illinoinensis"
    assert payload["input"]["recorded_not_used"]["extraction_method"] == "TRIzol kit"
    assert result["verification"]["quote_recheck"]["failed"] == 0
    assert payload["analysis_id"]
    stored = research.get_analysis(payload["analysis_id"])
    assert stored["analysis_id"] == payload["analysis_id"]


def test_a_pecan_analysis_markdown_report_is_honest_about_context() -> None:
    payload, status = research.analyse(
        {
            "problem": "Extract total RNA from pecan (Carya illinoinensis) embryos.",
            "organism": "Carya illinoinensis",
            "details": "We grind with a mortar and pestle.",
        }
    )
    assert status == 200
    report = research.analysis_markdown(payload["analysis_id"])
    assert "not used as evidence" in report
    assert "We grind with a mortar and pestle." in report
    assert "no RNA yield, RIN or degradation value is computed" in report
    assert "Quantitative yield available for target: False" in report
    assert "Direct evidence (target organism)" in report
    assert "Analogous evidence (hypotheses, not pecan measurements)" in report


def test_a_problem_outside_the_corpus_is_refused_with_no_result() -> None:
    payload, status = research.analyse(
        {
            "problem": "Extract total RNA from maize (Zea mays) leaves for RNA-seq.",
            "organism": "Zea mays",
            "tissue": "leaf",
            "molecule": "total RNA",
        }
    )
    assert status == 422
    assert payload["status"] == "refused"
    assert payload["execution_status"] == "not_applicable"
    assert payload["applicability"]["applicable"] is False
    assert payload["applicability"]["code"] == "evidence_not_applicable"
    assert "Carya illinoinensis" in payload["applicability"]["reason"]
    assert payload["result"] is None
    assert payload["analysis_id"] is None
    assert any(item["code"] == "workflow.encoding_failed" for item in payload["diagnostics"])


def test_an_unparsed_problem_is_refused_rather_than_guessed() -> None:
    payload, status = research.analyse({"problem": "We need RNA."})
    assert status == 422
    assert payload["status"] == "refused"
    assert payload["applicability"]["code"] == "problem_blocked"
    assert payload["result"] is None


def test_submission_validation_rejects_bad_input_without_running() -> None:
    with pytest.raises(research.ResearchError) as missing:
        research.analyse({"organism": "Carya illinoinensis"})
    assert missing.value.code == "problem_required"
    with pytest.raises(research.ResearchError) as unknown:
        research.analyse({"problem": "x", "model": "evil"})
    assert unknown.value.code == "unknown_field"
    with pytest.raises(research.ResearchError) as wrong_type:
        research.analyse({"problem": ["not", "a", "string"]})
    assert wrong_type.value.code == "invalid_field"
    with pytest.raises(research.ResearchError) as too_long:
        research.analyse({"problem": "x" * 4001})
    assert too_long.value.code == "field_too_long"



def test_feedback_reports_exactly_whether_it_was_stored(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(research, "FEEDBACK_DIR", "")
    absent = research.record_feedback({"message": "This is genuinely useful, thank you."})
    assert absent["persisted"] is False
    assert "not saved" in absent["note"]

    monkeypatch.setattr(research, "FEEDBACK_DIR", str(scratch / "feedback"))
    stored = research.record_feedback(
        {"message": "This is genuinely useful, thank you.", "role": "researcher"}
    )
    assert stored["persisted"] is True
    lines = (scratch / "feedback" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "This is genuinely useful, thank you."

    with pytest.raises(research.ResearchError) as too_short:
        research.record_feedback({"message": "ok"})
    assert too_short.value.code == "feedback_required"


def test_public_responses_contain_no_server_paths() -> None:
    payload, _status = research.analyse(
        {
            "problem": "Extract total RNA from pecan (Carya illinoinensis) embryos.",
            "organism": "Carya illinoinensis",
        }
    )
    public = json.dumps(app._public(payload), ensure_ascii=False)
    assert str(ROOT) not in public
    assert str(ROOT).replace("\\", "/") not in public
    assert "traceback" not in public


# ------------------------------------------------------------ the HTTP surface

@pytest.fixture(scope="module")
def base_url():
    """A real server on an ephemeral port, so the boundary is exercised as HTTP."""

    previous = app.RATE_LIMIT
    app.RATE_LIMIT = 10000
    httpd = app.BoundedThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        app.RATE_LIMIT = previous


def _request(base: str, path: str, body=None, method: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base + path, data=data, method=method or ("GET" if body is None else "POST")
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()



def test_the_page_is_served_by_the_python_host(base_url: str) -> None:
    status, headers, body = _request(base_url, "/research/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    page = body.decode("utf-8")
    for section in ("overview", "protocol", "evidence", "gaps", "analysis", "export"):
        assert f'id="{section}"' in page
    assert "Run analysis" in page
    assert "Privacy notice" in page
    assert "does not predict RNA yield" in page
    # No third-party scripts, no API key, no inline secrets.
    assert "<script src=\"http" not in page
    assert "apiKey" not in page and "API_KEY" not in page
    for asset in ("app.js", "style.css", "config.js"):
        assert asset in page

    status, headers, body = _request(base_url, "/research/app.js")
    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    status, headers, _ = _request(base_url, "/research/style.css")
    assert status == 200
    assert headers["Content-Type"].startswith("text/css")


def test_every_element_id_used_by_the_page_exists_in_it() -> None:
    page = (ROOT / "web" / "research" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "research" / "app.js").read_text(encoding="utf-8")
    declared = set(re.findall(r'id="([^"]+)"', page))
    used = set(re.findall(r'\$\(\s*\'([^\']+)\'\s*\)', script))
    used |= set(re.findall(r'getElementById\(\s*\'([^\']+)\'\s*\)', script))
    missing = sorted(used - declared)
    assert not missing, f"app.js references elements that the page does not define: {missing}"


def test_the_case_endpoint_serves_real_evidence_with_provenance(base_url: str) -> None:
    status, headers, body = _request(base_url, "/api/research/case")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    case = json.loads(body)
    assert case["origin"] == "composition/workflow_runs/pecan"
    assert len(case["claims"]) == 25
    for claim in case["claims"]:
        assert claim["source"]["doi"] or claim["source"]["pmcid"]
        assert claim["quote"]
        assert claim["evidence_class"] in {"direct", "analogue", "method_review"}
    assert str(ROOT) not in body.decode("utf-8")


def test_the_analysis_endpoint_executes_and_the_refusal_endpoint_refuses(
    base_url: str,
) -> None:
    status, _headers, body = _request(
        base_url,
        "/api/research/analysis",
        {
            "problem": "Extract total RNA from pecan (Carya illinoinensis) embryos.",
            "organism": "Carya illinoinensis",
            "extraction_method": "TRIzol",
        },
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "completed"
    analysis_id = payload["analysis_id"]
    assert analysis_id

    status, headers, body = _request(
        base_url, f"/api/research/runs/{analysis_id}/report.md"
    )
    assert status == 200
    assert headers["Content-Type"].startswith("text/markdown")
    assert b"Direct evidence (target organism)" in body

    status, _headers, body = _request(
        base_url,
        f"/api/research/runs/{analysis_id}/artifacts/model_spec",
    )
    assert status == 200
    assert json.loads(body)["model_id"] == "pecan_rna_evidence_audit"

    status, _headers, body = _request(
        base_url,
        "/api/research/analysis",
        {"problem": "Extract total RNA from maize (Zea mays) leaves.", "organism": "Zea mays"},
    )
    assert status == 422
    refusal = json.loads(body)
    assert refusal["status"] == "refused"
    assert refusal["result"] is None


def test_the_http_boundary_rejects_missing_input_and_traversal(base_url: str) -> None:
    status, _headers, body = _request(base_url, "/api/research/analysis", {})
    assert status == 400
    assert json.loads(body)["error"]["code"] == "problem_required"

    for path in (
        "/research/../api/app.py",
        "/research/%2e%2e/api/app.py",
        "/api/research/case/artifacts/..%2f..%2fapi%2fapp.py",
        "/api/research/case/artifacts/not_an_artifact",
        "/api/research/runs/00000000-0000-0000-0000-000000000000",
        "/api/research/unknown",
    ):
        status, _headers, _body = _request(base_url, path)
        assert status in {400, 404}, path


def test_feedback_over_http_says_what_happened(
    base_url: str, scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(research, "FEEDBACK_DIR", str(scratch / "feedback"))
    status, _headers, body = _request(
        base_url,
        "/api/research/feedback",
        {"message": "The evidence split is exactly what I needed.", "role": "researcher"},
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["persisted"] is True
    assert (scratch / "feedback" / "feedback.jsonl").is_file()

    status, _headers, body = _request(base_url, "/api/research/feedback", {"message": "short"})
    assert status == 400



# ------------------------------------------------------------- deployment

def test_the_image_recipe_copies_every_runtime_root() -> None:
    """Regression guard for a real failure: the workflow's worker root was missing.

    `execute.run_workflow` gives `JsonWorker` the package marker at
    `composition/workflow/model_package`; without it every manifest call fails and
    the graph is reported invalid. The staged-deployment test below reproduces the
    failure; this one keeps the recipe in step with the code.
    """

    dockerfile = (ROOT / "api" / "Dockerfile").read_text(encoding="utf-8")
    for path in (
        "api/research.py",
        "composition/composition",
        "composition/workflow",
        "composition/workflow_runs",
        "web/research",
    ):
        assert f"COPY {path}" in dockerfile, path
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (
        "!composition/workflow/",
        "!composition/workflow/**",
        "!composition/workflow_runs/**",
        "!web/research/**",
        "!api/research.py",
    ):
        assert pattern in ignore, pattern


def test_a_staged_deployment_runs_the_workflow_from_copies_only(
    scratch: Path,
) -> None:
    """Mirror the Dockerfile's runtime roots into a clean tree and run there.

    This is the deployment check that matters: it uses nothing outside the copied
    files, so a missing COPY line fails here rather than on the host.
    """

    import os
    import subprocess

    stage = scratch / "stage"
    stage.mkdir()
    shutil.copytree(ROOT / "composition" / "composition", stage / "composition" / "composition")
    shutil.copytree(ROOT / "composition" / "workflow", stage / "composition" / "workflow")
    (stage / "api").mkdir()
    shutil.copy(ROOT / "api" / "app.py", stage / "api" / "app.py")
    shutil.copy(ROOT / "api" / "research.py", stage / "api" / "research.py")
    shutil.copy(ROOT / "api" / "__init__.py", stage / "api" / "__init__.py")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(stage / "composition")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "composition.runner",
            "--run-workflow",
            "composition/workflow/fixtures/pecan/problem.json",
            "--repo-root",
            str(stage),
        ],
        cwd=str(stage / "composition"),
        capture_output=True,
        text=True,
        timeout=300,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    payload = json.loads(completed.stdout)
    assert payload["status"] == "success"
    assert payload["model"]["model_id"] == "pecan_rna_evidence_audit"
    assert payload["execution"]["status"] in {"success", "success_with_warnings"}
    # The app serves the page from the same tree.
    assert (stage / "composition" / "workflow" / "model_package" / "pyproject.toml").is_file()

