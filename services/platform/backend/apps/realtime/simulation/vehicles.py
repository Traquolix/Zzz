"""
Vehicle physics helpers — creation, movement, density.
"""

import random
import time
import uuid

from .constants import (
    DEFAULT_DAILY_TRAFFIC,
    FIBER_DAILY_TRAFFIC,
    METERS_PER_CHANNEL,
    MIN_GAP_CHANNELS,
    SAFE_FOLLOWING_SECONDS,
    VEHICLE_PROFILES,
    VEHICLE_TYPES,
)
from .types import FiberConfig, Vehicle


def _weighted_choice(items: list[str], weights: list[float]) -> str:
    total = sum(weights)
    r = random.random() * total
    for item, w in zip(items, weights, strict=False):
        r -= w
        if r <= 0:
            return item
    return items[-1]


def _get_max_channel(fiber: FiberConfig, direction: int) -> int:
    """Get the maximum valid channel for a fiber+direction."""
    if direction == 0 and fiber.max_channel_dir0 is not None:
        return fiber.max_channel_dir0
    if direction == 1 and fiber.max_channel_dir1 is not None:
        return fiber.max_channel_dir1
    return fiber.channel_count


def _create_vehicle(fiber: FiberConfig, channel: float, direction: int, lane: int) -> Vehicle:
    vtype = random.choice(VEHICLE_TYPES)
    profile = VEHICLE_PROFILES[vtype]
    # Use fiber's typical speed range for target speed
    low, high = fiber.typical_speed_range
    target = low + random.random() * (high - low)
    # Cap at vehicle profile max and fiber speed limit
    target = min(target, profile["max_speed"], fiber.speed_limit)
    return Vehicle(
        id=f"v-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
        fiber_line=fiber.id,
        channel=channel,
        speed=target * (0.7 + random.random() * 0.3),
        target_speed=target,
        direction=direction,
        lane=lane,
        vehicle_type=vtype,
        aggressiveness=random.random(),
        created_at=time.time(),
    )


def _update_vehicle(
    v: Vehicle,
    vehicles: list[Vehicle],
    fiber: FiberConfig,
    delta_s: float,
) -> Vehicle | None:
    """Update a single vehicle's speed and position using car-following physics.

    Vehicles only see other vehicles — they don't know about incidents.
    Road events work by setting forced_speed on the affected vehicle,
    which then naturally slows down traffic behind it via car-following.
    """
    profile = VEHICLE_PROFILES[v.vehicle_type]

    # Bounds check: remove vehicles outside valid channel range
    max_ch = _get_max_channel(fiber, v.direction)
    if v.channel < 0 or v.channel >= max_ch:
        return None
    if time.time() - v.created_at > 600:
        return None

    # Find vehicle ahead in same lane
    ahead = [
        o
        for o in vehicles
        if o.id != v.id
        and o.fiber_line == v.fiber_line
        and o.lane == v.lane
        and o.direction == v.direction
        and (
            (v.direction == 0 and o.channel > v.channel)
            or (v.direction == 1 and o.channel < v.channel)
        )
    ]
    if ahead:
        ahead.sort(key=lambda o: abs(o.channel - v.channel))
        vehicle_ahead = ahead[0]
    else:
        vehicle_ahead = None

    # Use forced_speed if this vehicle is affected by a road event
    effective_target = v.forced_speed if v.forced_speed is not None else v.target_speed

    # Car-following model (IDM-inspired)
    new_speed = v.speed
    if vehicle_ahead:
        gap = abs(vehicle_ahead.channel - v.channel) - profile["length"]
        safe_gap = MIN_GAP_CHANNELS + (v.speed / 3.6) * SAFE_FOLLOWING_SECONDS / METERS_PER_CHANNEL
        if gap < safe_gap:
            rel_speed = v.speed - vehicle_ahead.speed
            braking = min(1.0, (safe_gap - gap) / safe_gap + rel_speed / 50)
            new_speed -= profile["decel"] * delta_s * braking * (2 - v.aggressiveness)
        elif gap < safe_gap * 2:
            target_match = vehicle_ahead.speed * 0.95
            if v.speed > target_match:
                new_speed -= profile["decel"] * delta_s * 0.3
            else:
                new_speed += profile["accel"] * delta_s * 0.5
        else:
            if v.speed < effective_target:
                new_speed += profile["accel"] * delta_s
            elif v.speed > effective_target:
                new_speed -= profile["decel"] * delta_s * 0.5
    else:
        if v.speed < effective_target:
            new_speed += profile["accel"] * delta_s
        elif v.speed > effective_target:
            new_speed -= profile["decel"] * delta_s * 0.3

    new_speed = max(0.0, min(profile["max_speed"], new_speed))

    # Move
    m_per_ms = (new_speed * 1000) / 3_600_000
    ch_per_ms = m_per_ms / METERS_PER_CHANNEL
    ch_delta = ch_per_ms * (delta_s * 1000) * (1 if v.direction == 0 else -1)

    v.speed = new_speed
    v.channel += ch_delta
    return v


def _get_density_multiplier(sim_hour: float, fiber: FiberConfig | None) -> float:
    """Get traffic density multiplier for the current simulated hour."""
    curve = DEFAULT_DAILY_TRAFFIC
    if fiber is not None and fiber.daily_traffic is not None:
        curve = fiber.daily_traffic
    elif fiber is not None:
        curve = FIBER_DAILY_TRAFFIC.get(fiber.id, DEFAULT_DAILY_TRAFFIC)
    h = int(sim_hour) % 24
    h_next = (h + 1) % 24
    frac = sim_hour - int(sim_hour)
    return curve[h] + (curve[h_next] - curve[h]) * frac
