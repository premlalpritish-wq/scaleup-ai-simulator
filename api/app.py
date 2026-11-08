"""Small, bounded HTTP adapter around the registered Python composition engine.

The API accepts graph documents only. Model implementations, paths and Python
code are selected by the checked-in adapter registry, never by a request.
"""
from __future__ import annotations

import json
import ipaddress
import math
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "composition"
import sys

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from composition import __version__ as RUNNER_VERSION  # noqa: E402
from composition import cross_model, cross_paper  # noqa: E402
from composition.adapters import REGISTRATIONS, known_models  # noqa: E402
from composition.contracts import load_graph  # noqa: E402
from composition.quantities import describe_registry  # noqa: E402
from composition.runner import describe_model, run_graph  # noqa: E402
from composition.adapters.base import clear_worker_cache  # noqa: E402

if __package__:
    from . import research as research_api  # noqa: E402
else:  # imported as a bare module by the test suite
    import research as research_api  # noqa: E402

#: Static assets of the research explorer, served by this same service so one
#: Python host is enough for a public URL. Paths are allow-listed; no request
#: path is ever joined to the filesystem.
RESEARCH_STATIC: dict[str, tuple[Path, str]] = {
    "/research/": (ROOT / "web" / "research" / "index.html", "text/html; charset=utf-8"),
    "/research/index.html": (ROOT / "web" / "research" / "index.html", "text/html; charset=utf-8"),
    "/research/app.js": (ROOT / "web" / "research" / "app.js", "text/javascript; charset=utf-8"),
    "/research/style.css": (ROOT / "web" / "research" / "style.css", "text/css; charset=utf-8"),
    "/research/config.js": (ROOT / "web" / "research" / "config.js", "text/javascript; charset=utf-8"),
}


MAX_BODY_BYTES = int(os.environ.get("SCALEUP_MAX_BODY_BYTES", "262144"))
MAX_INSTANCES = int(os.environ.get("SCALEUP_MAX_INSTANCES", "2"))
MAX_CONNECTIONS = int(os.environ.get("SCALEUP_MAX_CONNECTIONS", "64"))
MAX_INPUTS = int(os.environ.get("SCALEUP_MAX_INPUTS", "256"))
MAX_CONCURRENT_RUNS = int(os.environ.get("SCALEUP_MAX_CONCURRENT_RUNS", "1"))
RATE_LIMIT = int(os.environ.get("SCALEUP_RATE_LIMIT_PER_MINUTE", "30"))
MAX_RETAINED_SIMULATIONS = int(os.environ.get("SCALEUP_RETAINED_SIMULATIONS", "5"))
RATE_WINDOW = 60.0
_run_slots = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)
_simulations: dict[str, dict[str, Any]] = {}
_sim_lock = threading.Lock()
REGISTERED = {entry.model_id: entry.model_version for entry in REGISTRATIONS}
_rate_lock = threading.Lock()
_requests: dict[str, deque[float]] = defaultdict(deque)


def _reject_json_constant(value: str) -> None:
    raise ValueError(value)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details


def _graph_from_request(body: Any) -> dict[str, Any]:
    graph = body.get("graph") if isinstance(body, dict) else None
    if not isinstance(graph, dict):
        raise ApiError(400, "graph_required", "Request JSON must contain a graph object.")
    def finite(value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, dict):
            return all(finite(item) for item in value.values())
        if isinstance(value, list):
            return all(finite(item) for item in value)
        return True
    if not finite(graph):
        raise ApiError(400, "non_finite_number", "Graph inputs and parameters must contain only finite JSON numbers.")
    if not isinstance(graph.get("instances", []), list) or not isinstance(graph.get("connections", []), list) or not isinstance(graph.get("literal_inputs", {}), dict):
        raise ApiError(400, "invalid_graph_shape", "Graph instances and connections must be arrays, and literal_inputs must be an object.")
    if len(graph.get("instances", [])) > MAX_INSTANCES:
        raise ApiError(413, "instance_limit", f"A graph may contain at most {MAX_INSTANCES} instances.")
    if len(graph.get("connections", [])) > MAX_CONNECTIONS:
        raise ApiError(413, "connection_limit", f"A graph may contain at most {MAX_CONNECTIONS} connections.")
    if len(graph.get("literal_inputs", {})) > MAX_INPUTS:
        raise ApiError(413, "input_limit", f"A graph may contain at most {MAX_INPUTS} literal inputs.")
    for instance in graph.get("instances", []):
        params = instance.get("parameters", {}) if isinstance(instance, dict) else {}
        simulation = params.get("simulation", {}) if isinstance(params, dict) else {}
        if isinstance(simulation, dict):
            duration = simulation.get("duration_h", 24)
            if isinstance(duration, (int, float)) and not 0 < duration <= 48:
                raise ApiError(413, "duration_limit", "Simulation duration must be greater than zero and at most 48 h.")
            times = simulation.get("output_times_h", [])
            if isinstance(times, list) and len(times) > 5001:
                raise ApiError(413, "trajectory_limit", "A trajectory may contain at most 5,001 requested output times.")
            solver = simulation.get("solver", {})
            if isinstance(solver, dict) and "h_max" in solver:
                h_max = solver["h_max"]
                if isinstance(h_max, (int, float)) and not 0.001 <= h_max <= 1:
                    raise ApiError(413, "solver_limit", "Solver maximum step must be between 0.001 and 1 h.")
            if isinstance(solver, dict):
                for key, lower, upper in (("rtol", 1e-8, 1e-3), ("atol", 1e-12, 1e-4)):
                    value = solver.get(key)
                    if isinstance(value, (int, float)) and not lower <= value <= upper:
                        raise ApiError(413, "solver_limit", f"Solver {key} must be between {lower:g} and {upper:g}.")
                for key, lower, upper in (("max_steps", 1, 200000), ("max_range_rejections", 1, 60)):
                    value = solver.get(key)
                    if key in solver and (not isinstance(value, int) or not lower <= value <= upper):
                        raise ApiError(413, "solver_limit", f"Solver {key} must be an integer between {lower} and {upper}.")
    if any(not isinstance(inst, dict) or not isinstance(inst.get("model_id"), str)
           for inst in graph.get("instances", [])):
        raise ApiError(400, "invalid_graph_shape", "Each graph instance must name a registered model id.")
    for instance in graph.get("instances", []):
        model_id = instance["model_id"]
        if model_id not in REGISTERED:
            raise ApiError(400, "unregistered_model", f"Model {model_id!r} is not in the server's registered model list.")
        version = instance.get("model_version")
        if version not in (None, "", "unversioned", REGISTERED[model_id]):
            raise ApiError(400, "unregistered_version", f"Version {version!r} is not registered for model {model_id!r}.")
    # load_graph rejects unknown fields and malformed structures before the engine
    # sees a payload; run_graph remains the authority for contracts and compatibility.
    try:
        load_graph(graph)
    except Exception as exc:
        raise ApiError(400, "invalid_graph", str(exc)) from None
    return graph


def _execution_payload(simulation_id: str, graph: dict[str, Any], result: dict[str, Any], exit_code: int) -> dict[str, Any]:
    successful = result.get("status") in {"success", "success_with_warnings"} and exit_code == 0
    trajectories: dict[str, dict[str, Any]] = {}
    model_validation: dict[str, dict[str, Any]] = {}
    for instance in result.get("results", []):
        summary = instance.get("raw_summary", {})
        instance_validation = {
            key: summary[key]
            for key in ("implementation_status", "reproduction_status", "validation_claim")
            if key in summary
        }
        model_validation[instance.get("instance_id", "unknown")] = instance_validation
        for output in instance.get("outputs", []):
            value = output.get("value", {})
            extra = value.get("extra", {})
            trajectory = extra.get("trajectory") if isinstance(extra, dict) else None
            if isinstance(extra, dict) and extra.get("validation_claim"):
                model_validation[instance.get("instance_id", "unknown")].setdefault("validation_claim", extra["validation_claim"])
            if trajectory:
                ref = output.get("ref", {})
                trajectories[f"{ref.get('instance_id')}/{ref.get('port_id')}"] = trajectory
    return {
        "simulation_id": simulation_id,
        "execution_status": "completed" if successful else "failed",
        "graph_id": result.get("graph_id", graph.get("graph_id")),
        "model_versions": result.get("model_versions", {}),
        "input_configuration": {"literal_inputs": graph.get("literal_inputs", {}), "instance_parameters": {item.get("instance_id"): item.get("parameters", {}) for item in graph.get("instances", [])}},
        "time_axis": next((t.get("time_axis") for t in trajectories.values() if t.get("time_axis")), None),
        "trajectories": trajectories,
        "quantity_definitions": describe_registry(),
        "diagnostics": result.get("diagnostics", []),
        "composition_report": result.get("composition_report", {}),
        "provenance": result.get("provenance_index", {}),
        "scientific_validation_status": {
            "execution_success": successful,
            "models": model_validation,
            "interpretation": "Execution success does not imply scientific validation.",
        },
        "result_kind": "computed" if successful else "none",
        "result": result,
    }


def _allow_rate(client: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        if len(_requests) > 10000:
            expired = [key for key, values in _requests.items() if not values or values[-1] <= now - RATE_WINDOW]
            for key in expired:
                _requests.pop(key, None)
        history = _requests[client]
        while history and history[0] <= now - RATE_WINDOW:
            history.popleft()
        if len(history) >= RATE_LIMIT:
            return False
        history.append(now)
    return True


def _client_key(peer_ip: str, forwarded_for: str | None = None, *, trust_proxy: bool = False) -> str:
    """Use the proxy-provided visitor IP only behind the configured host proxy."""
    if trust_proxy and forwarded_for:
        candidate = forwarded_for.split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(peer_ip))
    except ValueError:
        return "unknown"


def _public(value: Any) -> Any:
    """Remove server-only traceback and absolute project-path details."""
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if k not in {"traceback", "package"}}
    if isinstance(value, list):
        return [_public(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), "[server project root]").replace(str(ROOT).replace("\\", "/"), "[server project root]")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "ScaleUpExecutionAPI/1"
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} {self.client_address[0]} {fmt % args}")

    def _client_ip(self) -> str:
        trust_proxy = os.environ.get("SCALEUP_TRUST_FORWARDED_CLIENT_IP", "false").lower() == "true"
        return _client_key(self.client_address[0], self.headers.get("X-Forwarded-For"), trust_proxy=trust_proxy)

    def _cors(self) -> None:
        allowed = os.environ.get("SCALEUP_CORS_ORIGIN", "http://localhost:8000")
        origin = self.headers.get("Origin")
        if origin and (origin == allowed or allowed == "*"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, status: int, value: Any) -> None:
        data = json.dumps(_public(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, data: bytes, content_type: str, *, cache: str = "no-store") -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_research_error(self, exc: "research_api.ResearchError") -> None:
        self._send(
            exc.status,
            {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    def _body(self) -> Any:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise ApiError(400, "invalid_content_length", "Content-Length must be an integer.") from None
        if length < 1 or length > MAX_BODY_BYTES:
            raise ApiError(413, "request_size_limit", f"JSON body must be between 1 and {MAX_BODY_BYTES} bytes.")
        try:
            return json.loads(self.rfile.read(length), parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ApiError(400, "invalid_json", "Request body must be valid UTF-8 JSON.") from None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_research_get(self, path: str) -> bool:
        """Serve the research explorer page and its read-only endpoints.

        Returns True when the path belongs to the research surface, so the graph
        routes are untouched. Every path is allow-listed; a request string is
        never joined to the filesystem.
        """

        if path in RESEARCH_STATIC:
            target, content_type = RESEARCH_STATIC[path]
            if not target.is_file():
                raise research_api.ResearchError(
                    503,
                    "explorer_unavailable",
                    "The research explorer assets are not installed in this deployment.",
                )
            # Short-lived caching: a reload does not re-download the page on every
            # visit, and a deployment change reaches visitors within a minute.
            self._send_bytes(200, target.read_bytes(), content_type, cache="public, max-age=60")
            return True
        if path == "/api/research/case":
            self._send(200, research_api.load_case())
            return True
        if path == "/api/research/case/report.md":
            self._send_bytes(
                200,
                research_api.case_markdown().encode("utf-8"),
                "text/markdown; charset=utf-8",
            )
            return True
        if path.startswith("/api/research/case/artifacts/"):
            name = unquote(path[len("/api/research/case/artifacts/") :])
            self._send_bytes(
                200,
                research_api.case_artifact_path(name).read_bytes(),
                "application/json; charset=utf-8",
            )
            return True
        if path.startswith("/api/research/runs/"):
            rest = path[len("/api/research/runs/") :].split("/")
            run_id = unquote(rest[0])
            if len(rest) == 1 and run_id:
                self._send(200, research_api.get_analysis(run_id))
                return True
            if len(rest) == 2 and rest[1] == "report.md":
                self._send_bytes(
                    200,
                    research_api.analysis_markdown(run_id).encode("utf-8"),
                    "text/markdown; charset=utf-8",
                )
                return True
            if len(rest) == 3 and rest[1] == "artifacts" and run_id:
                name = unquote(rest[2])
                self._send_bytes(
                    200,
                    research_api.run_artifact_path(run_id, name).read_bytes(),
                    "application/json; charset=utf-8",
                )
                return True
            raise research_api.ResearchError(
                404, "not_found", "No research route matches this path."
            )
        return False

    def do_GET(self) -> None:
        try:
            if not _allow_rate(self._client_ip()):
                raise ApiError(429, "rate_limit", "Too many requests. Try again in one minute.")
            path = urlsplit(self.path).path
            if path in ("/", "/research"):
                self.send_response(302)
                self._cors()
                self.send_header("Location", "/research/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                if self._handle_research_get(path):
                    return
            except research_api.ResearchError as exc:
                return self._send_research_error(exc)
            if path == "/api/health":
                return self._send(200, {"status": "ok", "service": "scaleup-execution-api", "runner_version": RUNNER_VERSION})
            if path == "/api/models":
                return self._send(200, {"models": known_models(), "runner_version": RUNNER_VERSION})
            if path == "/api/default-graph":
                graph = json.loads((ROOT / "composition" / "examples" / "ganjave_fed_batch.json").read_text(encoding="utf-8"))
                return self._send(200, {"graph": graph, "source": "composition/examples/ganjave_fed_batch.json"})
            if path == "/api/connections":
                return self._send(200, cross_model.describe())
            parts = [unquote(p) for p in path.split("/") if p]
            if len(parts) == 4 and parts[:2] == ["api", "models"] and parts[3] == "contract":
                payload, code = describe_model(parts[2])
                return self._send(200 if code == 0 else 404, payload)
            if len(parts) == 3 and parts[:2] == ["api", "cross-paper-context"]:
                payload, code = cross_paper.context_for(parts[2])
                return self._send(200 if code == 0 else 404, payload)
            if len(parts) == 3 and parts[:2] == ["api", "simulations"]:
                with _sim_lock:
                    payload = _simulations.get(parts[2])
                if payload is None:
                    raise ApiError(404, "simulation_not_found", "No simulation exists with that identifier.")
                return self._send(200, payload)
            if len(parts) == 4 and parts[:2] == ["api", "simulations"] and parts[3] == "report":
                with _sim_lock:
                    payload = _simulations.get(parts[2])
                if payload is None:
                    raise ApiError(404, "simulation_not_found", "No simulation exists with that identifier.")
                return self._send(200, {"simulation_id": parts[2], "composition_report": payload["composition_report"], "provenance": payload["provenance"], "diagnostics": payload["diagnostics"]})
            raise ApiError(404, "not_found", "No API route matches this path.")
        except ApiError as exc:
            return self._send(exc.status, {"error": {"code": exc.code, "message": str(exc), "details": exc.details}})
        except Exception as exc:  # A service failure is structured; details stay server-side.
            print(f"GET {self.path} failed: {type(exc).__name__}: {exc}")
            return self._send(503, {"error": {"code": "service_unavailable", "message": "The execution service could not read project metadata."}})

    def do_POST(self) -> None:
        try:
            if not _allow_rate(self._client_ip()):
                raise ApiError(429, "rate_limit", "Too many requests. Try again in one minute.")
            path = urlsplit(self.path).path
            if path in ("/api/research/analysis", "/api/research/feedback"):
                body = self._body()
                try:
                    if path == "/api/research/feedback":
                        return self._send(200, research_api.record_feedback(body))
                    if not _run_slots.acquire(blocking=False):
                        raise ApiError(
                            503,
                            "execution_capacity",
                            "All execution slots are busy. Retry shortly.",
                        )
                    try:
                        payload, status = research_api.analyse(body)
                    finally:
                        clear_worker_cache()
                        _run_slots.release()
                    return self._send(status, payload)
                except research_api.ResearchError as exc:
                    return self._send_research_error(exc)
            body = self._body()
            graph = _graph_from_request(body)
            if path == "/api/validate":
                try:
                    result, code = run_graph(graph, plan_only=True, base=ROOT)
                finally:
                    clear_worker_cache()
                valid = code == 0 and result.get("status") not in {"invalid", "refused", "failed"}
                return self._send(200 if valid else 422, {"valid": valid, "graph_id": result.get("graph_id"), "diagnostics": result.get("diagnostics", []), "plan": result.get("plan", {}), "composition_report": result.get("composition_report", {})})
            if path != "/api/simulations":
                raise ApiError(404, "not_found", "No API route matches this path.")
            if not _run_slots.acquire(blocking=False):
                raise ApiError(503, "execution_capacity", "All model execution slots are busy. Retry shortly.")
            try:
                result, code = run_graph(graph, plan_only=False, base=ROOT)
            finally:
                clear_worker_cache()
                _run_slots.release()
            simulation_id = str(uuid.uuid4())
            payload = _execution_payload(simulation_id, graph, result, code)
            with _sim_lock:
                _simulations[simulation_id] = payload
                if len(_simulations) > MAX_RETAINED_SIMULATIONS:
                    oldest = next(iter(_simulations))
                    if oldest != simulation_id:
                        _simulations.pop(oldest, None)
            return self._send(200 if payload["execution_status"] == "completed" else 422, payload)
        except ApiError as exc:
            return self._send(exc.status, {"error": {"code": exc.code, "message": str(exc), "details": exc.details}})
        except Exception as exc:
            print(f"POST {self.path} failed: {type(exc).__name__}: {exc}")
            return self._send(503, {"error": {"code": "runner_unavailable", "message": "The model runner failed before producing a result. No previous result was reused."}})


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound simultaneous request-handler threads, including slow clients."""
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]):
        self._connection_slots = threading.BoundedSemaphore(32)
        super().__init__(address, handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


def serve() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = BoundedThreadingHTTPServer((host, port), Handler)
    print(f"ScaleUp execution API listening on {host}:{port} (runner {RUNNER_VERSION})")
    server.serve_forever()


if __name__ == "__main__":
    serve()
