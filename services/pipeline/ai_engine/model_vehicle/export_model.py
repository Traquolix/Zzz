#!/usr/bin/env python3
"""One-time script to re-export counting model from full-object to state_dict format.

Usage:
    python -m ai_engine.model_vehicle.export_model \
        --input vehicle_counting_model.pt \
        --output vehicle_counting_model_sd.pt

After running, update fibers.yaml to point to the new file and delete the old one.
"""

import argparse
from pathlib import Path

import torch


def main():
    parser = argparse.ArgumentParser(description="Re-export counting model to state_dict format")
    parser.add_argument("--input", required=True, help="Path to old .pt file (full object)")
    parser.add_argument("--output", required=True, help="Path for new .pt file (state_dict)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input model not found: {input_path}")

    # Load old format (full object, requires weights_only=False)
    print(f"Loading old model from {input_path}...")
    model = torch.load(input_path, map_location="cpu", weights_only=False)

    # Save as state_dict (can be loaded with weights_only=True)
    print(f"Saving state_dict to {output_path}...")
    torch.save(model.state_dict(), output_path)

    # Verify round-trip
    from ai_engine.model_vehicle.simple_interval_counter import build_counting_network

    verify_model = build_counting_network()
    verify_model.load_state_dict(torch.load(output_path, map_location="cpu", weights_only=True))
    verify_model.eval()

    print(f"Verified: model loads with weights_only=True")
    print(f"Next steps:")
    print(f"  1. Update fibers.yaml model_path to point to {output_path.name}")
    print(f"  2. Delete old model file: {input_path}")


if __name__ == "__main__":
    main()
