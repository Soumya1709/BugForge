import torch
import torch.nn as nn


class QNetwork(nn.Module):
    """
    QNetwork v3 — right-sized for BugForge dataset.

    Key insight: deeper != better when training data is small (240 examples).
    Original 3-layer network was fine in size, the missing pieces were:
      - Dropout (was overfitting)
      - LayerNorm on input (CodeBERT embeddings have large variance)
      - Kaiming init

    Architecture: 771 -> 256 -> 128 -> 8
    Same depth as original but properly regularized.
    """

    def __init__(self, state_size=771, action_size=8, dropout=0.3):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(state_size, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Dropout(dropout),

            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(dropout),

            nn.Linear(128, action_size),
        )

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_uniform_(m.weight, nonlinearity='relu')
                nn.init.constant_(m.bias, 0.0)

    def forward(self, x):
        return self.net(x)