"""
Self-Supervised DTAN Training Script
=====================================

Trains a DTAN (Diffeomorphic Temporal Alignment Network) per fiber using
the self-supervised loss from Khacef's PhD thesis (2024COAZ5070).

No labeled data needed — the data IS its own label. The model learns to
align channel n-1 to channel n using CPAB transformations.

Usage:
    # Train on preprocessed data (from preprocess_hdf5.py):
    python train_dtan.py \\
        --data-dir /path/to/training_data/carros/full \\
        --output-dir /path/to/models/dtan_carros_retrained \\
        --fiber-id carros \\
        --epochs 120 \\
        --lr 1e-4

    # Quick test run:
    python train_dtan.py \\
        --data-dir /path/to/training_data/carros/full \\
        --output-dir /tmp/dtan_test \\
        --fiber-id carros \\
        --epochs 5 \\
        --max-windows 1000

Requirements:
    pip install torch numpy matplotlib
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

import numpy as np

PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
class DASWindowDataset(Dataset):
    """Dataset of sliding windows from preprocessed DAS data.

    Each window is [Nch, signal_len] extracted from the processed section data.
    Windows slide along the spatial (channel) axis with overlap.

    Args:
        data_dir: Directory with .npy chunk files from preprocess_hdf5.py
        section_name: Section name (e.g., "default", "section1") - used for logging only
        n_channels: Number of channels per window (Nch, default 9)
        signal_len: Signal length per window (default 300 = 30s at 10Hz)
        stride_channels: Channel stride between windows (default 1 = max overlap)
        stride_time: Time stride in samples (default signal_len = no overlap)
        max_windows: Maximum number of windows to extract (for testing)
    """

    def __init__(
        self,
        data_dir: str,
        section_name: str = "default",
        n_channels: int = 9,
        signal_len: int = 300,
        stride_channels: int = 1,
        stride_time: Optional[int] = None,
        max_windows: Optional[int] = None,
    ):
        self.n_channels = n_channels
        self.signal_len = signal_len
        self.stride_channels = stride_channels
        self.stride_time = stride_time or signal_len

        # Load all chunks for this section
        # Support multiple naming conventions:
        # 1. {section}_chunk{idx}.npy (original format)
        # 2. {date}_chunk{idx}.npy (preprocessing v2 format)
        # 3. *chunk*.npy (fallback)
        data_path = Path(data_dir)
        chunk_files = sorted(data_path.glob(f"{section_name}_chunk*.npy"))

        if not chunk_files:
            # Try date-prefixed format (YYYYMMDD_chunk*.npy)
            chunk_files = sorted(data_path.glob("*_chunk*.npy"))

        if not chunk_files:
            # Final fallback
            chunk_files = sorted(data_path.glob("*.npy"))

        if not chunk_files:
            raise FileNotFoundError(
                f"No chunk files found in {data_dir}. "
                f"Expected files like '{section_name}_chunk0000.npy' or 'YYYYMMDD_chunk0000.npy'"
            )

        logger.info(f"Loading {len(chunk_files)} chunks for section '{section_name}'")

        chunks = [np.load(str(f)) for f in chunk_files]
        self.data = np.concatenate(chunks, axis=0)  # [n_samples, n_channels_section]

        logger.info(
            f"Section data: {self.data.shape} "
            f"({self.data.shape[0] / 10:.1f}s at 10Hz, {self.data.shape[1]} channels)"
        )

        # Extract windows
        self.windows = self._extract_windows(max_windows)
        logger.info(f"Extracted {len(self.windows)} windows ({n_channels}ch x {signal_len}samples)")

    def _extract_windows(self, max_windows: Optional[int] = None) -> List[np.ndarray]:
        """Extract all windows from the data."""
        n_samples, n_total_ch = self.data.shape
        windows = []

        for t_start in range(0, n_samples - self.signal_len + 1, self.stride_time):
            for ch_start in range(0, n_total_ch - self.n_channels + 1, self.stride_channels):
                window = self.data[
                    t_start : t_start + self.signal_len,
                    ch_start : ch_start + self.n_channels,
                ].T  # [Nch, signal_len]

                # Z-score normalize
                mean = window.mean()
                std = window.std()
                if std < 1e-8:
                    continue  # Skip dead windows
                window = (window - mean) / std

                windows.append(window.astype(np.float32))

                if max_windows and len(windows) >= max_windows:
                    return windows

        return windows

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        return torch.from_numpy(self.windows[idx])


# ---------------------------------------------------------------------------
# Training Loop
# ---------------------------------------------------------------------------
def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    criterion,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> dict:
    """Train for one epoch.

    Args:
        model: DTAN model
        dataloader: Training data loader
        criterion: DTANLoss instance
        optimizer: Optimizer
        device: Device

    Returns:
        Dictionary of average losses
    """
    model.train()
    total_losses = {"total": 0, "reconstruction": 0, "inner": 0, "inter": 0}
    n_batches = 0

    for batch in dataloader:
        batch = batch.to(device)  # [batch_size, Nch, signal_len]

        # Forward pass: get aligned output and thetas
        aligned, thetas = model(batch, return_theta=True)

        # Compute loss
        losses = criterion(batch, aligned, thetas)

        # Backward pass
        optimizer.zero_grad()
        losses["total"].backward()
        optimizer.step()

        for key in total_losses:
            total_losses[key] += losses[key].item()
        n_batches += 1

    return {k: v / max(n_batches, 1) for k, v in total_losses.items()}


def validate(
    model: nn.Module,
    dataloader: DataLoader,
    criterion,
    device: torch.device,
) -> dict:
    """Validate model performance.

    Args:
        model: DTAN model
        dataloader: Validation data loader
        criterion: DTANLoss instance
        device: Device

    Returns:
        Dictionary of average losses
    """
    model.eval()
    total_losses = {"total": 0, "reconstruction": 0, "inner": 0, "inter": 0}
    n_batches = 0

    with torch.no_grad():
        for batch in dataloader:
            batch = batch.to(device)
            aligned, thetas = model(batch, return_theta=True)
            losses = criterion(batch, aligned, thetas)

            for key in total_losses:
                total_losses[key] += losses[key].item()
            n_batches += 1

    return {k: v / max(n_batches, 1) for k, v in total_losses.items()}


def generate_before_after_plots(
    model: nn.Module,
    dataset: DASWindowDataset,
    device: torch.device,
    output_dir: str,
    fiber_id: str,
    n_examples: int = 5,
):
    """Generate before/after alignment visualization.

    Args:
        model: Trained DTAN model
        dataset: Dataset with windows
        device: Device
        output_dir: Output directory
        fiber_id: Fiber identifier
        n_examples: Number of examples to plot
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    model.eval()

    fig, axes = plt.subplots(n_examples, 3, figsize=(18, 4 * n_examples))
    if n_examples == 1:
        axes = axes.reshape(1, 3)

    indices = np.linspace(0, len(dataset) - 1, n_examples, dtype=int)

    for i, idx in enumerate(indices):
        window = dataset[idx].unsqueeze(0).to(device)  # [1, Nch, signal_len]

        with torch.no_grad():
            aligned, thetas = model(window, return_theta=True)

        window_np = window[0].cpu().numpy()
        aligned_np = aligned[0].cpu().numpy()
        thetas_np = thetas[0].cpu().numpy()

        # Before alignment
        vmax = np.percentile(np.abs(window_np), 99)
        axes[i, 0].imshow(window_np, aspect="auto", cmap="seismic", vmin=-vmax, vmax=vmax)
        axes[i, 0].set_title(f"Before (window {idx})")
        axes[i, 0].set_ylabel("Channel")

        # After alignment
        vmax_a = np.percentile(np.abs(aligned_np), 99)
        axes[i, 1].imshow(aligned_np, aspect="auto", cmap="seismic", vmin=-vmax_a, vmax=vmax_a)
        axes[i, 1].set_title("After DTAN alignment")

        # Theta parameters
        axes[i, 2].imshow(thetas_np, aspect="auto", cmap="coolwarm")
        axes[i, 2].set_title(f"Theta (max={np.abs(thetas_np).max():.3f})")
        axes[i, 2].set_ylabel("Channel")
        axes[i, 2].set_xlabel("Theta dim")

    for ax in axes[-1, :2]:
        ax.set_xlabel("Time sample")

    plt.suptitle(f"DTAN Before/After — {fiber_id}", fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"before_after_{fiber_id}.png"), dpi=150)
    plt.close()
    logger.info("Saved before/after visualization")


def plot_training_curves(history: List[dict], output_dir: str, fiber_id: str):
    """Plot training and validation loss curves.

    Args:
        history: List of dicts with train/val losses per epoch
        output_dir: Output directory
        fiber_id: Fiber identifier
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    epochs = range(1, len(history) + 1)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    for idx, key in enumerate(["total", "reconstruction", "inner", "inter"]):
        ax = axes[idx // 2, idx % 2]
        train_vals = [h[f"train_{key}"] for h in history]
        val_vals = [h[f"val_{key}"] for h in history]

        ax.plot(epochs, train_vals, label="Train", linewidth=1)
        ax.plot(epochs, val_vals, label="Val", linewidth=1)
        ax.set_title(f"{key} loss")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.suptitle(f"Training Curves — {fiber_id}", fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"training_curves_{fiber_id}.png"), dpi=150)
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Self-Supervised DTAN Training")
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory with preprocessed .npy files (from preprocess_hdf5.py)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for trained model and visualizations",
    )
    parser.add_argument("--fiber-id", type=str, required=True, help="Fiber identifier (for naming)")
    parser.add_argument(
        "--section",
        type=str,
        default="default",
        help="Section name to train on (default: 'default')",
    )

    # Model hyperparameters (from thesis)
    parser.add_argument(
        "--signal-len",
        type=int,
        default=300,
        help="Signal length per window (default: 300 = 30s at 10Hz)",
    )
    parser.add_argument(
        "--n-channels", type=int, default=9, help="Channels per window (default: 9)"
    )
    parser.add_argument(
        "--tess-size", type=int, default=20, help="CPAB tessellation size (thesis: 20)"
    )

    # Training hyperparameters
    parser.add_argument("--epochs", type=int, default=120, help="Number of epochs (thesis: 120)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (thesis: 1e-4)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lambda-inner", type=float, default=1.0, help="Inner regularizer weight")
    parser.add_argument(
        "--lambda-inter", type=float, default=1.0, help="Inter-channel regularizer weight"
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.3, help="Validation ratio (thesis: 0.3)"
    )

    # Data parameters
    parser.add_argument(
        "--stride-channels", type=int, default=1, help="Channel stride for window extraction"
    )
    parser.add_argument(
        "--stride-time", type=int, default=None, help="Time stride in samples (default: signal_len)"
    )
    parser.add_argument(
        "--max-windows", type=int, default=None, help="Maximum windows to extract (for testing)"
    )

    # Device
    parser.add_argument(
        "--device", type=str, default="auto", help="Device: 'cuda', 'cpu', or 'auto'"
    )

    # Pretrained weights
    parser.add_argument(
        "--pretrained",
        type=str,
        default=None,
        help="Path to pretrained model weights (for fine-tuning)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Device
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    logger.info(f"Using device: {device}")

    # Load dataset
    logger.info(f"Loading data from {args.data_dir}")
    full_dataset = DASWindowDataset(
        data_dir=args.data_dir,
        section_name=args.section,
        n_channels=args.n_channels,
        signal_len=args.signal_len,
        stride_channels=args.stride_channels,
        stride_time=args.stride_time,
        max_windows=args.max_windows,
    )

    # Train/val split (thesis: 70/30)
    n_total = len(full_dataset)
    n_val = int(n_total * args.val_ratio)
    n_train = n_total - n_val

    train_dataset, val_dataset = torch.utils.data.random_split(
        full_dataset,
        [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
    )

    logger.info(f"Dataset: {n_train} train, {n_val} val windows")

    # Create model
    from ai_engine.model_vehicle.DTAN import DTAN

    device_type = "gpu" if device.type == "cuda" else "cpu"
    device_name = str(device) if device.type == "cuda" else "cpu"

    model = DTAN(
        signal_len=args.signal_len,
        Nch=args.n_channels,
        channels=1,
        tess_size=[args.tess_size],
        bidirectional_RNN=True,  # Must match inference (model_T.py uses True)
        zero_boundary=True,
        device=device_type,
        device_name=device_name,
    ).to(device)

    # Load pretrained weights if provided
    if args.pretrained:
        logger.info(f"Loading pretrained weights from {args.pretrained}")
        state_dict = torch.load(args.pretrained, map_location=device, weights_only=True)
        model.load_state_dict(state_dict, strict=False)

    # Count parameters
    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Model: {n_params:,} parameters ({n_trainable:,} trainable)")

    # Loss and optimizer
    from .loss import DTANLoss

    criterion = DTANLoss(
        lambda_inner=args.lambda_inner,
        lambda_inter=args.lambda_inter,
    )

    # Initialize CPA covariance from model's CPAB basis (Thesis Eq. 2.21)
    cpab_basis = model.T.get_basis()  # Get CPAB transformation basis
    criterion.set_cpa_covariance_from_basis(cpab_basis)
    criterion = criterion.to(device)
    logger.info(
        "Initialized CPA covariance matrix from CPAB basis (thesis-compliant Mahalanobis norm)"
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    # Training loop
    history = []
    best_val_loss = float("inf")

    logger.info(f"\nStarting training: {args.epochs} epochs, lr={args.lr}")
    logger.info(f"Loss weights: lambda_inner={args.lambda_inner}, lambda_inter={args.lambda_inter}")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()

        train_losses = train_epoch(model, train_loader, criterion, optimizer, device)
        val_losses = validate(model, val_loader, criterion, device)

        epoch_time = time.time() - t0

        # Record history
        epoch_record = {}
        for key in train_losses:
            epoch_record[f"train_{key}"] = train_losses[key]
            epoch_record[f"val_{key}"] = val_losses[key]
        history.append(epoch_record)

        # Save best model
        if val_losses["total"] < best_val_loss:
            best_val_loss = val_losses["total"]
            torch.save(model.state_dict(), str(output_dir / "best.pt"))
            best_marker = " *BEST*"
        else:
            best_marker = ""

        # Log progress
        if epoch % 5 == 0 or epoch == 1:
            logger.info(
                f"Epoch {epoch:3d}/{args.epochs}: "
                f"train={train_losses['total']:.6f} "
                f"(recon={train_losses['reconstruction']:.6f}, "
                f"inner={train_losses['inner']:.6f}, "
                f"inter={train_losses['inter']:.6f}) | "
                f"val={val_losses['total']:.6f} | "
                f"{epoch_time:.1f}s{best_marker}"
            )

    # Save final model
    torch.save(model.state_dict(), str(output_dir / "final.pt"))

    # Save training config
    config = {
        "fiber_id": args.fiber_id,
        "section": args.section,
        "signal_len": args.signal_len,
        "n_channels": args.n_channels,
        "tess_size": args.tess_size,
        "epochs": args.epochs,
        "lr": args.lr,
        "batch_size": args.batch_size,
        "lambda_inner": args.lambda_inner,
        "lambda_inter": args.lambda_inter,
        "val_ratio": args.val_ratio,
        "n_train": n_train,
        "n_val": n_val,
        "best_val_loss": best_val_loss,
        "device": str(device),
    }
    with open(str(output_dir / "config.json"), "w") as f:
        json.dump(config, f, indent=2)

    # Generate visualizations
    logger.info("\nGenerating visualizations...")
    plot_training_curves(history, str(output_dir), args.fiber_id)
    generate_before_after_plots(model, full_dataset, device, str(output_dir), args.fiber_id)

    logger.info("\nTraining complete!")
    logger.info(f"  Best val loss: {best_val_loss:.6f}")
    logger.info(f"  Model saved to: {output_dir}")
    logger.info(f"  Best weights: {output_dir / 'best.pt'}")


if __name__ == "__main__":
    main()
