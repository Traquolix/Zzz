"""SHM frequency reading generator.

Generates simulated structural health monitoring data for infrastructure
items (bridges, tunnels). Uses a simplified physics model with periodic
oscillation, fast vibration, and random noise.

Note: the simulation engine (simulation/engine.py) has its own
generate_shm_readings with additional load_factor and traffic_amp terms.
"""

import math
import random
import time


def generate_shm_readings(infrastructure: list[dict], shm_state: dict) -> list[dict]:
    """
    Generate SHM frequency readings for infrastructure items.

    Simplified physics model (no vehicle-count dependency):
    - Base frequency: bridge ~5Hz, tunnel ~15Hz
    - Periodic + fast oscillation + random noise
    - Amplitude based on traffic load approximation

    Args:
        infrastructure: List of infrastructure dicts with 'id', 'type', 'fiber_id'.
        shm_state: Mutable dict for per-item state (base_freq, phase).
            Populated on first call; caller must persist between calls.

    Returns:
        List of SHM reading dicts ready for frontend broadcast.
    """
    now_ms = int(time.time() * 1000)
    t = time.time()
    readings = []

    for infra in infrastructure:
        iid = infra["id"]

        if iid not in shm_state:
            infra_type = infra.get("type", "bridge")
            base = {"bridge": 5.0, "tunnel": 15.0}.get(infra_type, 10.0)
            shm_state[iid] = {
                "base_freq": base + (random.random() - 0.5) * 2,
                "phase": random.random() * math.pi * 2,
            }

        state = shm_state[iid]
        base_freq = state["base_freq"]
        phase = state["phase"]

        periodic = math.sin(t * 0.1 + phase) * 0.3
        fast = math.sin(t * 2.5 + phase * 2) * 0.1
        noise = (random.random() - 0.5) * 0.2
        freq = base_freq + periodic + fast + noise

        base_amp = 0.3
        vib_amp = abs(math.sin(t * 5 + phase)) * 0.15
        noise_amp = random.random() * 0.1
        amp = min(1.0, base_amp + vib_amp + noise_amp)

        readings.append(
            {
                "infrastructureId": iid,
                "fiberId": infra.get("fiber_id", ""),
                "frequency": round(freq, 2),
                "amplitude": round(amp, 2),
                "timestamp": now_ms,
            }
        )

    return readings
