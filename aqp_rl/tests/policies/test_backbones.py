"""Hermetic tests for RL policy backbones."""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from aqp_rl.policies import (
    AutoencoderBackbone,
    PatchTSTBackbone,
    RecurrentBackbone,
    TimeSeriesEncoder,
    TransformerBackbone,
    build_backbone_from_alias,
)


def test_transformer_forward_3d_input():
    bb = TransformerBackbone(input_features=5, sequence_length=8, output_dim=16, n_heads=2, n_layers=1)
    x = np.random.randn(3, 8, 5).astype(np.float32)
    y = bb.forward(x)
    assert tuple(y.shape) == (3, 16)


def test_transformer_forward_flat_input_reshapes():
    bb = TransformerBackbone(input_features=5, sequence_length=8, output_dim=16, n_heads=2, n_layers=1)
    flat = np.random.randn(3, 40).astype(np.float32)
    y = bb.forward(flat)
    assert tuple(y.shape) == (3, 16)


@pytest.mark.parametrize("cell", ["lstm", "gru", "rnn"])
def test_recurrent_backbone_per_cell(cell):
    bb = RecurrentBackbone(
        input_features=4, sequence_length=10, output_dim=12,
        cell=cell, hidden_size=8, num_layers=2,
    )
    x = np.random.randn(2, 10, 4).astype(np.float32)
    y = bb.forward(x)
    assert tuple(y.shape) == (2, 12)


def test_autoencoder_forward():
    bb = AutoencoderBackbone(
        input_features=20, sequence_length=1, output_dim=8,
        hidden_dims=[64, 32], bottleneck_dim=8,
    )
    x = np.random.randn(4, 20).astype(np.float32)
    y = bb.forward(x)
    assert tuple(y.shape) == (4, 8)


def test_patchtst_num_patches_correct():
    bb = PatchTSTBackbone(
        input_features=3, sequence_length=12, output_dim=8,
        patch_length=4, d_model=8, n_heads=2, n_layers=1,
    )
    assert bb.num_patches == 3
    x = np.random.randn(2, 12, 3).astype(np.float32)
    y = bb.forward(x)
    assert tuple(y.shape) == (2, 8)


def test_patchtst_rejects_seq_shorter_than_patch():
    with pytest.raises(ValueError, match="too short"):
        PatchTSTBackbone(input_features=3, sequence_length=2, output_dim=8, patch_length=4)


def test_registry_lookup_by_alias():
    for alias in ("TransformerBackbone", "RecurrentBackbone", "AutoencoderBackbone", "PatchTSTBackbone"):
        bb = build_backbone_from_alias(
            alias, input_features=3, sequence_length=8, output_dim=4,
            backbone_kwargs={"n_heads": 1, "n_layers": 1, "d_ff": 8}
                if "Transformer" in alias else {"hidden_dims": [8]}
                if alias == "AutoencoderBackbone" else {"patch_length": 2, "d_model": 4, "n_heads": 1, "n_layers": 1, "d_ff": 8}
                if alias == "PatchTSTBackbone" else {"hidden_size": 4, "num_layers": 1},
        )
        assert isinstance(bb, TimeSeriesEncoder)


def test_rl_kind_registered():
    from aqp_rl.core.base import RL_KIND_POLICY_BACKBONE, list_rl_components

    components = list_rl_components(kind=RL_KIND_POLICY_BACKBONE)
    for needed in ("TransformerBackbone", "RecurrentBackbone", "AutoencoderBackbone", "PatchTSTBackbone"):
        assert needed in components


def test_unknown_alias_raises():
    with pytest.raises(KeyError, match="Unknown policy backbone"):
        build_backbone_from_alias("NonexistentBackbone", input_features=3, sequence_length=8)


def test_autoencoder_freeze_default_when_pretrained_path():
    bb = AutoencoderBackbone(
        input_features=4, sequence_length=1, output_dim=4,
        pretrained_path="/nonexistent/path/missing.pt",
    )
    # Default freeze_encoder = True when pretrained_path is supplied
    assert bb.freeze_encoder is True
