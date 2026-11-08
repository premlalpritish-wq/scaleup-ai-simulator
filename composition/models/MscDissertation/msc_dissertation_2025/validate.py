"""Self-checks for MSc Dissertation (2025) package."""
from typing import Any
from .manifest import build_manifest
from .model import simulate_extraction, simulate_trajectory

def validate() -> dict[str, Any]:
    checks = []
    # 1. Manifest valid
    m = build_manifest()
    checks.append({"id": "manifest", "ok": bool(m.get("ports")), "detail": "manifest contains ports"})

    # 2. Simulation valid
    res = simulate_extraction(t=16.0, biomass=15.0)
    ok_yield = 0.30 <= res["product_yield"] <= 0.35
    checks.append({"id": "yield", "ok": ok_yield, "detail": f"scaled yield = {res['product_yield']:.4f}"})

    # 3. Trajectory valid
    traj = simulate_trajectory(duration_h=20.0, n_points=41)
    ok_traj = len(traj["time_hours"]) == 41 and traj["product_yield_g_per_g"][-1] > 0.30
    checks.append({"id": "trajectory", "ok": ok_traj, "detail": "trajectory produced 41 time points"})

    all_ok = all(c["ok"] for c in checks)
    return {"ok": all_ok, "checks": checks}
