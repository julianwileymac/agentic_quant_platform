"""Smoke tests for Phase-5 paper-grade backbones.

Each backbone is validated for:

1. ``RLComponent`` metaclass registration with the expected
   ``rl_kind='rl_policy_backbone'`` + ``rl_alias``.
2. Subclass of :class:`TimeSeriesEncoder`.
3. ``forward(x)`` runs on a random tensor of the declared input shape
   and produces a tensor of the declared output shape.
4. ``forward`` accepts both flat ``(B, D)`` inputs and 3D
   ``(B, T, F)`` / 4D ``(B, F, N, T)`` inputs where applicable.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from aqp_rl.core.base import RL_KIND_POLICY_BACKBONE, list_rl_components
from aqp_rl.policies.backbones import (
    DualHeadContinuousBackbone,
    EIIEConvBackbone,
    HFTQBackbone,
    MarketScorerBackbone,
    PDDualRNNBackbone,
    SAGCNBackbone,
    SARLClassifierBackbone,
    TimeSeriesEncoder,
)


@pytest.mark.parametrize(
    "alias,cls",
    [
        ("eiie_conv", EIIEConvBackbone),
        ("sagcn", SAGCNBackbone),
        ("market_scorer", MarketScorerBackbone),
        ("hft_qnet", HFTQBackbone),
        ("eteo_dual_head", DualHeadContinuousBackbone),
        ("pd_dual_rnn", PDDualRNNBackbone),
        ("sarl_lstm", SARLClassifierBackbone),
    ],
)
def test_backbones_registered(alias: str, cls: type) -> None:
    registry = list_rl_components(RL_KIND_POLICY_BACKBONE)
    assert alias in registry, f"alias {alias!r} not in registry {sorted(registry)}"
    assert registry[alias] is cls
    assert issubclass(cls, TimeSeriesEncoder)


def test_eiie_conv_forward_shape():
    bb = EIIEConvBackbone(input_features=3, sequence_length=10, output_dim=4, n_assets=3, kernel_size=3)
    # (B, F, N, T)
    x = torch.randn(2, 3, 3, 10)
    out = bb.forward(x)
    assert out.shape == (2, 4)
    # Each row sums to ~1 (softmax across cash + 3 tickers).
    assert torch.allclose(out.sum(dim=1), torch.ones(2), atol=1e-5)


def test_eiie_conv_flat_input_reshapes():
    bb = EIIEConvBackbone(input_features=2, sequence_length=5, output_dim=3, n_assets=2)
    x = torch.randn(4, 2 * 2 * 5)  # (B, F·N·T)
    out = bb.forward(x)
    assert out.shape == (4, 3)


def test_sagcn_forward_shape():
    bb = SAGCNBackbone(
        input_features=3,
        sequence_length=8,
        output_dim=4,
        n_assets=5,
        hidden_dim=16,
        layers=2,
    )
    x = torch.randn(2, 3, 5, 8)
    out = bb.forward(x)
    assert out.shape == (2, 5 * 4)


def test_market_scorer_forward_shape():
    bb = MarketScorerBackbone(input_features=4, sequence_length=10, output_dim=2)
    x = torch.randn(2, 10, 4)
    out = bb.forward(x)
    assert out.shape == (2, 2)


def test_market_scorer_invalid_output_dim_raises():
    with pytest.raises(ValueError):
        MarketScorerBackbone(input_features=4, sequence_length=10, output_dim=3)


def test_hft_q_forward_with_concatenated_input():
    """HFT backbone accepts ``[state, prev_action, mask]`` concatenated input."""
    bb = HFTQBackbone(input_features=10, sequence_length=1, output_dim=5)
    # Layout: [state (10), prev_action (1), mask (5)] = 16
    state = torch.randn(2, 10)
    prev_a = torch.tensor([[2.0], [0.0]])
    mask = torch.tensor([[1, 1, 0, 0, 1], [1, 0, 1, 1, 0]], dtype=torch.float32)
    x = torch.cat([state, prev_a, mask], dim=-1)
    out = bb.forward(x)
    assert out.shape == (2, 5)
    # Masked actions get a large negative offset.
    # Row 0: actions 2, 3 are masked ⇒ value is very negative.
    assert out[0, 2].item() < -1e10
    assert out[0, 3].item() < -1e10


def test_hft_q_forward_split_explicit():
    bb = HFTQBackbone(input_features=8, output_dim=3)
    state = torch.randn(4, 8)
    prev_a = torch.tensor([0, 1, 2, 0])
    mask = torch.ones(4, 3)
    out = bb.forward_split(state, prev_a, mask)
    assert out.shape == (4, 3)


def test_dual_head_forward_shape():
    bb = DualHeadContinuousBackbone(input_features=5, sequence_length=10, output_dim=5)
    x = torch.randn(3, 5 * 10)
    out = bb.forward(x)
    assert out.shape == (3, 5)  # (μ_v, σ_v, μ_p, σ_p, V)


def test_dual_head_invalid_output_dim_raises():
    with pytest.raises(ValueError):
        DualHeadContinuousBackbone(input_features=5, sequence_length=10, output_dim=4)


def test_pd_dual_rnn_forward_shape():
    bb = PDDualRNNBackbone(
        input_features=4,
        sequence_length=10,
        output_dim=3,
        private_feature_dim=2,
        private_sequence_length=10,
    )
    public_flat = 4 * 10
    private_flat = 2 * 10
    x = torch.randn(2, public_flat + private_flat)
    out = bb.forward(x)
    assert out.shape == (2, 3)
    # sigma must be positive.
    assert (out[:, 1] > 0).all()


def test_pd_dual_rnn_explicit_split():
    bb = PDDualRNNBackbone(input_features=4, sequence_length=5, output_dim=3, private_feature_dim=2)
    public = torch.randn(2, 5, 4)
    private = torch.randn(2, 5, 2)
    out = bb.forward_split(public, private)
    assert out.shape == (2, 3)


def test_sarl_classifier_forward_shape():
    bb = SARLClassifierBackbone(input_features=3, sequence_length=8, output_dim=2)
    x = torch.randn(4, 8, 3)
    out = bb.forward(x)
    assert out.shape == (4, 2)
    # Outputs sum to 1 (softmax).
    assert torch.allclose(out.sum(dim=1), torch.ones(4), atol=1e-5)


def test_sarl_classifier_accepts_flat_input():
    bb = SARLClassifierBackbone(input_features=3, sequence_length=4, output_dim=3)
    x = torch.randn(2, 3 * 4)
    out = bb.forward(x)
    assert out.shape == (2, 3)
