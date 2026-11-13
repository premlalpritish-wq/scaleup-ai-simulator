import os
import sys
import json
import socket
import webbrowser
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from .solver_bridge import run_grounded_simulation

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
ARTIFACTS_DIR = PROJECT_ROOT / ".artifacts"

class ScaleUpSimulationHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static files from web/ by default
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/workbench", "/rag_workbench.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            wb_file = WEB_DIR / "rag_workbench.html"
            with open(wb_file, "rb") as f:
                self.wfile.write(f.read())
            return

        elif path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "scaleup_rag"}).encode("utf-8"))
            return

        elif path == "/api/latest_scene":
            art_file = ARTIFACTS_DIR / "rag_simulation_run.json"
            if art_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                with open(art_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "No simulation artifact found yet")
            return

        elif path == "/api/simulate":
            # Support GET with query param: /api/simulate?prompt=...
            qs = parse_qs(parsed.query)
            prompt = qs.get("prompt", ["Simulate E. coli fed-batch fermentation with 500 g/L glucose feed at 37 C"])[0]
            try:
                result = run_grounded_simulation(prompt=prompt)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Simulation solver error: {e}")
            return

        # Fallback to standard static file serving from PROJECT_ROOT
        # Handle /pre-reformer/* mapping directly to web/pre-reformer/*
        if path.startswith("/pre-reformer/"):
            rel_file = WEB_DIR / path.lstrip("/")
            if rel_file.exists() and rel_file.is_file():
                self.send_response(200)
                if path.endswith(".js"):
                    self.send_header("Content-Type", "application/javascript")
                elif path.endswith(".css"):
                    self.send_header("Content-Type", "text/css")
                self.end_headers()
                with open(rel_file, "rb") as f:
                    self.wfile.write(f.read())
                return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/simulate":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            try:
                req_data = json.loads(post_body.decode("utf-8")) if post_body else {}
                prompt = req_data.get("prompt", "Simulate E. coli fed-batch fermentation with 500 g/L glucose feed at 37 C")
                result = run_grounded_simulation(prompt=prompt)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Simulation solver error: {e}")
            return

        return super().do_POST()

def find_available_port(start_port: int = 8000, max_attempts: int = 50) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port

def start_server(port: int = 8000, open_browser: bool = True, block: bool = True) -> ThreadingHTTPServer:
    actual_port = find_available_port(port)
    server = ThreadingHTTPServer(("127.0.0.1", actual_port), ScaleUpSimulationHandler)
    url = f"http://127.0.0.1:{actual_port}/rag_workbench.html"

    print(f"ScaleUp 3D Simulation Workbench Server running at: {url}")
    if open_browser:
        webbrowser.open(url)

    if block:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down ScaleUp 3D Server.")
            server.server_close()
    else:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

    return server

if __name__ == "__main__":
    start_server(8000, open_browser=True, block=True)
