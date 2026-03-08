"""
Shared broadcast helpers for the realtime app.

Used by both the Kafka bridge (live flow) and the simulation engine (sim flow).
"""


async def broadcast_shm(
    channel_layer,
    readings: list[dict],
    infra_org_map: dict[str, str],
    flow: str,
):
    """Broadcast SHM readings to org-scoped groups via infrastructure ownership."""
    message = {
        "type": "broadcast_message",
        "channel": "shm_readings",
        "data": readings,
    }
    await channel_layer.group_send(f"realtime_{flow}_shm_readings_org___all__", message)

    org_readings: dict[str, list[dict]] = {}
    for shm in readings:
        org_id = infra_org_map.get(str(shm["infrastructureId"]), "")
        if org_id:
            org_readings.setdefault(org_id, []).append(shm)

    for org_id, org_data in org_readings.items():
        await channel_layer.group_send(
            f"realtime_{flow}_shm_readings_org_{org_id}",
            {"type": "broadcast_message", "channel": "shm_readings", "data": org_data},
        )
