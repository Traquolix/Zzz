from __future__ import annotations

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

    class nn:
        class Module:
            pass

    torch = None

try:
    from .libcpab import Cpab
    CPAB_AVAILABLE = True
except ImportError as e:
    CPAB_AVAILABLE = False
    raise ImportError(f"libcpab import failed: {e}")


class DTAN(nn.Module):
    """Diffeomorphic Temporal Alignment Network.

    Neural network for temporal alignment of multi-channel signals using
    CPAB (Continuous Piecewise-Affine Based) transformations.

    Args:
        signal_len: Signal length in samples
        Nch: Number of channels
        channels: Number of input channels (typically 1)
        tess_size: Tessellation shape for CPAB
        bidirectional_RNN: Use bidirectional RNN
        zero_boundary: Zero boundary constraint for CPAB
        device: Device type ('gpu' or 'cpu')
        device_name: Device name ('cuda:0' or 'cpu')
    """

    def __init__(
        self,
        signal_len: int = 300,
        Nch: int = 9,
        channels: int = 1,
        tess_size: list = None,
        bidirectional_RNN: bool = False,
        zero_boundary: bool = True,
        device: str = "gpu",
        device_name: str = "cuda:0",
    ):
        super(DTAN, self).__init__()

        if tess_size is None:
            tess_size = [6]

        self.T = Cpab(
            tess_size,
            backend="pytorch",
            device=device,
            device_name=device_name,
            zero_boundary=zero_boundary,
            volume_perservation=False,
        )
        self.tess_size = tess_size
        self.dim = self.T.get_theta_dim()
        self.input_shape = signal_len
        self.Nch = Nch
        self.channels = channels
        self.bidirectional_RNN = bidirectional_RNN

        D = 2 if self.bidirectional_RNN else 1

        self.localization = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=(2, 15)),
            nn.MaxPool2d((1, 4), stride=(1, 4)),
            nn.ReLU(True),
            nn.Conv2d(64, 32, kernel_size=(1, 9)),
            nn.MaxPool2d((1, 3), stride=(1, 3)),
            nn.ReLU(True),
            nn.Conv2d(32, 16, kernel_size=(1, 7)),
            nn.MaxPool2d((1, 2), stride=(1, 2)),
            nn.ReLU(True),
        )

        self.fc_input_dim = self.get_conv_to_fc_dim()

        self.fc_loc = nn.Sequential(
            nn.Linear(D * self.fc_input_dim, 128),
            nn.ReLU(True),
            nn.Linear(128, self.dim),
            nn.Tanh(),
        )

        self.RNN1 = nn.Sequential(
            nn.RNN(
                input_size=self.fc_input_dim,
                hidden_size=self.fc_input_dim,
                nonlinearity="relu",
                batch_first=True,
                num_layers=2,
                bidirectional=self.bidirectional_RNN,
            ),
        )

    def get_conv_to_fc_dim(self) -> int:
        rand_tensor = torch.rand([1, self.channels, self.Nch, self.input_shape])
        out_tensor = self.localization(rand_tensor)
        return out_tensor.size(1) * out_tensor.size(3)

    def predict_thetas(self, x: torch.Tensor) -> torch.Tensor:
        """Run only the CNN+RNN+FC head to predict transformation parameters.

        Skips the CPAB transform entirely. Use this when you need thetas
        but will compute the grid transform separately (e.g., with a cached grid).

        Args:
            x: Input tensor (batch_size, Nch, signal_length)

        Returns:
            thetas: (batch_size, Nch-1, theta_dim) transformation parameters
        """
        xs = self.localization(x.unsqueeze(dim=1))
        xs = torch.swapaxes(xs, 1, 2)
        xs = torch.flatten(xs, start_dim=2, end_dim=3)
        out_rnn1, _ = self.RNN1(xs)
        return self.fc_loc(out_rnn1)

    def stn(self, x: torch.Tensor, return_theta: bool = False, return_theta_and_transformed_grid: bool = False):
        """Spatial transformer network forward function.

        Args:
            x: Input tensor (batch_size, Nch, signal_length)
            return_theta: Return transformation parameters
            return_theta_and_transformed_grid: Return both theta and grid

        Returns:
            Transformed output, optionally with theta and/or grid
        """
        batch_size = x.shape[0]
        Nch = x.shape[1]

        xs = self.localization(x.unsqueeze(dim=1))

        xs = torch.swapaxes(xs, 1, 2)
        xs = torch.flatten(xs, start_dim=2, end_dim=3)

        out_rnn1, _ = self.RNN1(xs)
        thetas = self.fc_loc(out_rnn1)

        thetas_flatten = torch.flatten(thetas, start_dim=0, end_dim=1)

        x = torch.flatten(x[:, :-1], start_dim=0, end_dim=1)

        if return_theta_and_transformed_grid:
            output, grid_t = self.T.transform_data(
                x.unsqueeze(dim=1),
                thetas_flatten,
                outsize=(self.input_shape,),
                return_transformed_grid=True,
            )

            output = output.squeeze().reshape(batch_size, Nch - 1, self.input_shape)
            grid_t = grid_t.squeeze().reshape(batch_size, Nch - 1, self.input_shape)

            return output, thetas, grid_t

        elif return_theta:
            output = self.T.transform_data(x.unsqueeze(dim=1), thetas_flatten, outsize=(self.input_shape,))

            output = output.squeeze().reshape(batch_size, Nch - 1, self.input_shape)
            return output, thetas

        else:
            output = self.T.transform_data(x.unsqueeze(dim=1), thetas_flatten, outsize=(self.input_shape,))

            output = output.squeeze().reshape(batch_size, Nch - 1, self.input_shape)
            return output

    def forward(self, x: torch.Tensor, return_theta: bool = False, return_theta_and_transformed_grid: bool = False):
        """Forward pass through the DTAN network.

        Args:
            x: Input tensor (batch_size, Nch, signal_length)
            return_theta: Return transformation parameters
            return_theta_and_transformed_grid: Return both theta and grid

        Returns:
            Transformed output, optionally with theta and/or grid
        """
        return self.stn(x, return_theta, return_theta_and_transformed_grid)

    def get_basis(self):
        """Returns the CPAB transformation basis."""
        return self.T
