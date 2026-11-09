"""
Verification script for Electromechanical Doorbell coupled ODE simulation.
Validates the physical equations:
  1. Electrical RL Circuit: dI/dt = (V - I*R) / L when x <= x_break, else I = 0
  2. Reluctance Force: F_mag = (mu_0 * N^2 * I^2 * A) / (2 * g^2)
  3. Mechanical Kinematics: m * d^2x/dt^2 = F_mag - k*x - c*(dx/dt)
  4. Hybrid Discontinuous Impacts:
     - Bell strike at x = x_strike (restitution bounce)
     - Contact backstop at x = 0 (restitution bounce)
"""

import math
import sys

def verify_doorbell_ode(
    voltage: float = 9.0,
    resistance: float = 1.5,
    inductance: float = 0.005,
    coil_turns: int = 200,
    core_area: float = 0.0001,
    armature_mass: float = 0.015,
    spring_constant: float = 40.0,
    damping_coeff: float = 0.15,
    initial_air_gap: float = 0.005,
    contact_break_distance: float = 0.0015,
    chime_strike_distance: float = 0.004,
    min_air_gap: float = 0.0002,
    restitution_chime: float = 0.35,
    restitution_backstop: float = 0.20,
    sim_duration: float = 2.0,
    dt: float = 0.0001,
) -> dict:
    mu_0 = 4.0 * math.pi * 1e-7

    # Analytical sanity checks:
    I_max = voltage / resistance
    F_spring_break = spring_constant * contact_break_distance
    # Air gap at contact break
    g_at_break = max(min_air_gap, initial_air_gap - contact_break_distance)
    F_mag_max_at_break = (mu_0 * (coil_turns ** 2) * (I_max ** 2) * core_area) / (2.0 * (g_at_break ** 2))
    
    print("=" * 80)
    print("ELECTROMECHANICAL DOORBELL ODE MATHEMATICAL VERIFICATION")
    print("=" * 80)
    print(f"Max steady-state current I_max: {I_max:.2f} A")
    print(f"Spring restoring force at break point (x = {contact_break_distance*1000:.2f} mm): {F_spring_break:.4f} N")
    print(f"Max magnetic force at break point: {F_mag_max_at_break:.4f} N")
    
    # Check strict condition: F_mag(I_max) > k * x_break
    assert F_mag_max_at_break > F_spring_break, (
        f"Stall condition! Magnetic force ({F_mag_max_at_break} N) must exceed spring restoring force ({F_spring_break} N) at break threshold."
    )
    print(f"PASS: F_mag ({F_mag_max_at_break:.3f} N) > F_spring ({F_spring_break:.3f} N) by ratio {F_mag_max_at_break/F_spring_break:.1f}x")

    # Time integration (Semi-Implicit Euler with sub-stepping)
    steps = int(sim_duration / dt)
    x = 0.0
    v = 0.0
    I = 0.0
    
    strikes = 0
    break_events = 0
    strike_timestamps = []
    was_closed = True
    
    for step in range(steps):
        t = step * dt
        
        # 1. Electrical State
        contact_closed = (x <= contact_break_distance)
        if contact_closed:
            dI_dt = (voltage - I * resistance) / inductance
            I += dI_dt * dt
            if not was_closed:
                was_closed = True
        else:
            I = 0.0
            if was_closed:
                was_closed = False
                break_events += 1

        # 2. Reluctance Force
        g = max(min_air_gap, initial_air_gap - x)
        F_mag = (mu_0 * (coil_turns ** 2) * (I ** 2) * core_area) / (2.0 * (g ** 2))

        # 3. Mechanical Kinematics
        F_spring = -spring_constant * x
        F_damp = -damping_coeff * v
        F_total = F_mag + F_spring + F_damp

        a = F_total / armature_mass
        v += a * dt
        x += v * dt

        # 4. Impacts
        if x >= chime_strike_distance:
            x = chime_strike_distance
            if v > 0.0:
                v = -restitution_chime * v
                strikes += 1
                strike_timestamps.append(t)

        if x <= 0.0:
            x = 0.0
            if v < 0.0:
                v = -restitution_backstop * v

    # Strike frequency analysis
    intervals = []
    for i in range(1, len(strike_timestamps)):
        intervals.append(strike_timestamps[i] - strike_timestamps[i-1])

    avg_hz = 0.0
    if len(intervals) >= 10:
        recent = intervals[-20:]
        avg_dt = sum(recent) / len(recent)
        avg_hz = 1.0 / avg_dt

    print(f"Total simulated time: {sim_duration:.1f} s")
    print(f"Total contact break cycles: {break_events}")
    print(f"Total bell strikes: {strikes}")
    print(f"Calculated average strike frequency: {avg_hz:.1f} Hz")
    
    # Assert self-sustaining oscillation
    assert strikes >= 20, f"Simulation failed to produce sustainable oscillation! Only {strikes} strikes recorded."
    assert 20.0 <= avg_hz <= 100.0, f"Strike frequency {avg_hz} Hz out of expected electromechanical doorbell range (20-100 Hz)."
    print("SUCCESS: ODE physics model verified with sustainable stable limit-cycle oscillation!")
    print("=" * 80)
    
    return {
        "status": "VERIFIED",
        "strikes": strikes,
        "break_events": break_events,
        "avg_frequency_hz": avg_hz,
        "I_max": I_max,
        "F_mag_at_break": F_mag_max_at_break,
        "F_spring_at_break": F_spring_break
    }

if __name__ == "__main__":
    result = verify_doorbell_ode()
    print("Verification payload:", result)
