# aqp_index debt — RL production enhancement (Phases 0-12 + cross-cutting)

**Reason for debt note**: Per
`.cursor/rules/aqp-index-reflect.mdc`, the production-enhancement
changes touch the following qualifying surfaces that require an
`aqp_index/` refresh:

- New top-level packages under `aqp_rl/src/aqp_rl/`:
  `analytical/`, `evaluation/`, `replay/`, `validation/`.
- New public surface (`__init__.py` re-exports) in
  `aqp_rl/src/aqp_rl/{agents, envs, observations, experiments,
  policies/backbones, rewards}/__init__.py`.
- New analysis flow under `aqp/analysis/flows/`.
- New `BaseDataset` kind under `aqp/data/datasets/kinds/`.
- New FinAgent tool tree under `aqp/agents/tools/finagent/`.
- New `configs/agents/finagent/` directory + 5 YAMLs.
- New `aqp_rl/configs/{analytical, validation, evaluation,
  experiments, envs}/` directories + ~20 representative YAMLs.
- 3 new `aqp_docs/` pages
  (`rl-market-dynamics.md`, `rl-prudex-evaluation.md`,
  `rl-finagent.md`).
- 1 new ADR (`aqp_docs/architecture/decisions/010-rl-production-enhancement.md`).
- `aqp_docs/rl-framework.md` updated with Phase 1-12 component
  table + new doc cross-links.

**Files to refresh on the next curator pass**:

- `aqp_index/project-index.md` — add Phase 1-12 component aliases
  to the RL summary section.
- `aqp_index/architecture-pointers.md` — pin Phase 6
  (Market Dynamics), Phase 9 (PRUDEX), Phase 10 (FinAgent) as
  cross-subsystem touchpoints (RL ↔ Analysis ↔ Agents).
- `aqp_index/skills-registry.md` — register the new
  paper-grade-agent / validation-suite / PRUDEX skills.
- `aqp_index/subagents-registry.md` — no changes needed (no new
  subagents introduced).
- Token-saving code indices under `aqp_index/code-indices/` —
  refresh `rl-framework.md`, `rl-iceberg.md`, and add new entries
  for `aqp_rl/{analytical,evaluation,replay,validation}/__init__.py`
  signatures.

**Summary**: ~40 new registered `RLComponent` aliases land across
Phases 1-12. All compose with existing infrastructure
(`RLRuntime`, `WeightCentricPipeline`, `IcebergTrajectoryStore`,
`router_complete`, `AgentRuntime`, `AnalysisRuntime`) and respect
every hard rule in `aqp_rl/AGENTS.md`. See
[ADR-010](../../aqp_docs/architecture/decisions/010-rl-production-enhancement.md)
for the full rationale + trade-offs.

**Acceptance**: Every phase has a corresponding test directory
under `aqp_rl/tests/`. Aggregate pass count:

| Phase | Test dir | Tests | Status |
| --- | --- | --- | --- |
| 1 | `aqp_rl/tests/rewards/` | 58 | passing |
| 2 | `aqp_rl/tests/analytical/` | 27 | passing |
| 3 | `aqp_rl/tests/envs/test_tradesim_envs.py` | 19 | passing |
| 4 | `aqp_rl/tests/agents/` | 14 | passing |
| 5 | `aqp_rl/tests/policies/test_paper_grade_backbones.py` | 20 | passing |
| 6 | `aqp_rl/tests/mdm/` | 14 | passing |
| 7 | `aqp_rl/tests/imputation/` | 6 | passing |
| 8 | `aqp_rl/tests/validation/` | 29 | passing |
| 9 | `aqp_rl/tests/evaluation/` | 11 | passing |
| 10 | `aqp_rl/tests/finagent/` | 12 | passing |
| 11 | `aqp_rl/tests/replay/` | 14 | passing |
| 12 | `aqp_rl/tests/execution/test_live_parity.py` | 9 | passing |
| **Total** | | **233** | **all passing** |

**Curator action**: refresh on the next scheduled pass; no urgent
production debt.
