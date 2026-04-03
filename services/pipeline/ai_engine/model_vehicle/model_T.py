from __future__ import annotations

import logging
import os
from pathlib import Path

from .DTAN import DTAN

logger = logging.getLogger(__name__)

# Module directory for reliable path resolution
_MODULE_DIR = Path(__file__).parent.resolve()

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


class Args_NN_model_all_channels:
    """Configuration for DTAN model and inference.

    Model weights (.pth files) are loaded from ai_engine/model_vehicle/models_parameters/.
    These weights are shared across all fibers — a single DTAN model handles
    vehicle detection regardless of fiber. Per-fiber calibration differences
    are handled at the calibration stage (calibration.py), not in the model.

    Args:
        data_window_length: Length of input data window in samples
        gauge: Sensor gauge distance in meters
        Nch: Number of channels per section
        N_channels: Number of channel overlaps
        fs: Sampling frequency (Hz)
        exp_name: Experiment name for model file
        version: Model version string
        models_path: Path to models directory
    """

    def __init__(
        self,
        data_window_length: int,
        gauge: float,
        Nch: int,
        N_channels: int,
        fs: float,
        exp_name: str,
        version: str,
        models_path: str = "models_parameters",
        bidirectional_rnn: bool = True,
    ):
        self.exp_name = exp_name
        self.version = version
        self.fs = fs
        self.gauge = gauge
        self.Nch = Nch
        self.signal_length = data_window_length
        self.input_shape = data_window_length
        self.N_channels = N_channels

        self.tess_size = 20
        self.bidirectional_RNN = bidirectional_rnn
        self.zero_boundary = False

        if TORCH_AVAILABLE and torch.backends.mps.is_available():
            self.batch_size = 64
        elif TORCH_AVAILABLE and torch.cuda.is_available():
            self.batch_size = 128
        else:
            self.batch_size = 32

        # Use module directory for reliable path resolution
        self.model_path = _MODULE_DIR / models_path / f"{self.exp_name}_parameters_{self.version}.pth"

        if TORCH_AVAILABLE:
            if torch.cuda.is_available():
                self.device = "gpu"
                self.device_name = "cuda:0"
            elif torch.backends.mps.is_available():
                self.device = "cpu"
                self.device_name = "cpu"
            else:
                self.device = "cpu"
                self.device_name = "cpu"
        else:
            self.device = "cpu"
            self.device_name = "cpu"

    def get_model_Theta(self) -> tuple:
        """Creates and loads the DTAN model.

        Returns:
            Tuple of (CPAB_basis, model)
        """
        model = DTAN(
            signal_len=self.input_shape,
            Nch=self.Nch,
            channels=1,
            tess_size=[self.tess_size],
            bidirectional_RNN=self.bidirectional_RNN,
            zero_boundary=self.zero_boundary,
            device=self.device,
            device_name=self.device_name,
        )

        map_location = torch.device("cuda:0") if self.device == "gpu" else torch.device("cpu")
        model_parameters = torch.load(
            self.model_path, map_location=map_location, weights_only=True
        )

        model.load_state_dict(model_parameters)

        if self.device == "gpu":
            model = model.to("cuda:0")

        if self.device == "cpu":
            cpu_count = os.cpu_count() or 4
            torch.set_num_threads(cpu_count)

        T = model.get_basis()
        return T, model
