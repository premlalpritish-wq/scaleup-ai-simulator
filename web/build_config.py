"""Render a safe API-origin configuration for static hosting builds."""
import json
import os
from pathlib import Path

base = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
if base and not base.startswith("https://"):
    raise SystemExit("API_BASE_URL must use HTTPS in hosted builds")
Path("config.js").write_text(
    "window.SCALEUP_API_BASE = " + json.dumps(base) + ";\n", encoding="utf-8"
)
