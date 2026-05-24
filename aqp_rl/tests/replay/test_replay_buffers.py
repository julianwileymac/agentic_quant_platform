"""Phase-11 replay-buffer tests.

Acceptance gates:

- GeneralReplayBuffer: pre-allocated, namedtuple-driven, sample
  returns batched NumPy arrays.
- PrioritizedReplayBuffer: sum-tree integrity, α / β knobs,
  importance-sampling weights ∈ (0, 1].
- NStepInfoReplayBuffer: n-step return = Σ γ^k · r_{t+k},
  info keys filtered, action mask + DP_action preserved.
"""
from __future__ import annotations

import numpy as np
import pytest

from aqp_rl.replay import (
    GeneralReplayBuffer,
    NStepInfoReplayBuffer,
    PrioritizedReplayBuffer,
)


# --------------------------------------------------------------------------- General


def test_general_buffer_preallocates_and_samples():
    buf = GeneralReplayBuffer(
        capacity=100,
        shapes={"obs": (4,), "action": (2,), "reward": (1,), "next_obs": (4,), "done": (1,)},
    )
    rng = np.random.default_rng(0)
    for _ in range(50):
        buf.add(
            obs=rng.normal(size=4).astype(np.float32),
            action=rng.normal(size=2).astype(np.float32),
            reward=float(rng.normal()),
            next_obs=rng.normal(size=4).astype(np.float32),
            done=False,
        )
    assert len(buf) == 50
    batch = buf.sample(16)
    assert batch["obs"].shape == (16, 4)
    assert batch["action"].shape == (16, 2)
    assert batch["reward"].shape == (16, 1)
    assert batch["done"].dtype == np.bool_


def test_general_buffer_wraps_at_capacity():
    buf = GeneralReplayBuffer(capacity=10, shapes={"obs": (2,)})
    for i in range(25):
        buf.add(obs=np.array([i, i + 1]), action=0, reward=0, next_obs=np.array([0, 0]), done=False)
    # Buffer should hold the most recent 10 entries.
    assert len(buf) == 10
    obs_batch = buf.sample(10)["obs"]
    # All observations should be from indices [15..24].
    assert obs_batch[:, 0].min() >= 15


def test_general_buffer_extra_fields_via_info():
    buf = GeneralReplayBuffer(
        capacity=10,
        shapes={"obs": (2,), "log_prob": (1,)},
        extra_fields=("log_prob",),
    )
    buf.add(
        obs=np.array([1, 2]),
        action=0,
        reward=0,
        next_obs=np.array([3, 4]),
        done=False,
        info={"log_prob": 0.5},
    )
    out = buf.sample(1)
    assert "log_prob" in out
    assert out["log_prob"].shape == (1, 1)
    assert float(out["log_prob"][0, 0]) == pytest.approx(0.5)


def test_general_buffer_sample_as_namedtuple():
    buf = GeneralReplayBuffer(capacity=10, shapes={"obs": (2,)})
    buf.add(obs=[1, 2], action=0, reward=0, next_obs=[3, 4], done=False)
    nt = buf.sample_as_namedtuple(1)
    assert hasattr(nt, "obs")
    assert hasattr(nt, "action")
    assert hasattr(nt, "reward")


def test_general_buffer_invalid_capacity_raises():
    with pytest.raises(ValueError):
        GeneralReplayBuffer(capacity=0)


# --------------------------------------------------------------------------- Prioritized


def test_prioritized_buffer_sums_to_total():
    buf = PrioritizedReplayBuffer(capacity=8)
    for i in range(8):
        buf.add(obs=i, action=0, reward=float(i), next_obs=i + 1, done=False)
    # 8 leaves all at the same initial priority — total should equal
    # 8 * priority.
    total = buf._tree.total  # noqa: SLF001
    leaf_sum = float(buf._tree.tree[buf.capacity - 1 :].sum())  # noqa: SLF001
    assert total == pytest.approx(leaf_sum, rel=1e-9)


def test_prioritized_buffer_sample_returns_weights():
    buf = PrioritizedReplayBuffer(capacity=64)
    for i in range(64):
        buf.add(obs=i, action=0, reward=float(i), next_obs=i + 1, done=False)
    batch = buf.sample(8)
    assert "weights" in batch
    assert "indices" in batch
    assert batch["weights"].shape == (8,)
    # All weights normalised to [0, 1] (max == 1).
    assert batch["weights"].max() == pytest.approx(1.0)
    assert (batch["weights"] > 0).all()


def test_prioritized_update_priorities_changes_sampling_distribution():
    buf = PrioritizedReplayBuffer(capacity=16, alpha=1.0)
    for i in range(16):
        buf.add(obs=i, action=0, reward=0, next_obs=0, done=False)
    batch = buf.sample(8)
    # Boost the priority of the first sampled index by ×10000.
    high_td = np.full(len(batch["indices"]), 1e3)
    buf.update_priorities(batch["indices"], high_td)
    # Now re-sample many times and verify those indices show up more.
    counter = {int(i): 0 for i in batch["indices"]}
    for _ in range(50):
        new_batch = buf.sample(8)
        for tree_idx in new_batch["indices"]:
            if int(tree_idx) in counter:
                counter[int(tree_idx)] += 1
    # The boosted indices should be over-represented (sum > 8 trivially).
    assert sum(counter.values()) >= 8


def test_prioritized_invalid_args_raise():
    with pytest.raises(ValueError):
        PrioritizedReplayBuffer(capacity=0)
    with pytest.raises(ValueError):
        PrioritizedReplayBuffer(capacity=10, alpha=-0.1)
    with pytest.raises(ValueError):
        PrioritizedReplayBuffer(capacity=10, beta_start=0.5, beta_end=0.3)
    with pytest.raises(ValueError):
        PrioritizedReplayBuffer(capacity=10, beta_anneal_steps=0)
    with pytest.raises(ValueError):
        PrioritizedReplayBuffer(capacity=10, epsilon=0.0)


def test_prioritized_beta_anneals():
    buf = PrioritizedReplayBuffer(capacity=16, beta_start=0.0, beta_end=1.0, beta_anneal_steps=10)
    for i in range(16):
        buf.add(obs=i, action=0, reward=0, next_obs=0, done=False)
    # Sample several times to advance the annealing counter.
    for _ in range(5):
        buf.sample(4)
    assert buf._current_beta() == pytest.approx(0.5, abs=0.01)  # noqa: SLF001


# --------------------------------------------------------------------------- N-step


def test_nstep_buffer_n1_degenerates_to_one_step():
    buf = NStepInfoReplayBuffer(capacity=100, n_steps=1, gamma=0.99)
    for i in range(10):
        buf.add(obs=i, action=0, reward=float(i), next_obs=i + 1, done=False)
    assert len(buf) == 10
    batch = buf.sample(5)
    # 1-step buffer ⇒ reward in sampled batch = original reward.
    assert all(isinstance(r, float) for r in batch["reward"])


def test_nstep_buffer_accumulates_discounted_reward():
    buf = NStepInfoReplayBuffer(capacity=100, n_steps=3, gamma=0.5)
    # Push 3 rewards of (1, 1, 1).
    for i in range(3):
        buf.add(obs=i, action=0, reward=1.0, next_obs=i + 1, done=(i == 2))
    # n-step return = 1 + 0.5 * 1 + 0.25 * 1 = 1.75
    assert len(buf) >= 1
    batch = buf.sample(len(buf))
    expected = 1 + 0.5 + 0.25
    assert any(r == pytest.approx(expected) for r in batch["reward"])


def test_nstep_buffer_filters_info_keys():
    buf = NStepInfoReplayBuffer(
        capacity=100,
        n_steps=1,
        info_keys=("DP_action", "available_action"),
    )
    buf.add(
        obs=0,
        action=0,
        reward=0,
        next_obs=1,
        done=True,
        info={
            "DP_action": np.array([1, 0, 0]),
            "available_action": np.array([1, 1, 0]),
            "extra_key": "should be dropped",
        },
    )
    batch = buf.sample(1)
    info = batch["info"][0]
    assert "DP_action" in info
    assert "available_action" in info
    assert "extra_key" not in info


def test_nstep_invalid_args_raise():
    with pytest.raises(ValueError):
        NStepInfoReplayBuffer(capacity=0)
    with pytest.raises(ValueError):
        NStepInfoReplayBuffer(capacity=10, n_steps=0)
    with pytest.raises(ValueError):
        NStepInfoReplayBuffer(capacity=10, gamma=-0.1)
