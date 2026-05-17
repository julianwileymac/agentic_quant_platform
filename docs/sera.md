# SERA — Open Coding Agents (Ai2) as an AQP LLM provider

> Status: **opt-in**. Defaults are disabled; the operator wires SERA in
> when they want repo-specialised code generation for the
> `codebase_refactorer` agent (or any other AgentSpec that prefers
> code-tuned weights).

[`SERA`](https://allenai.org/blog/open-coding-agents) — *Soft-Verified
Efficient Repository Agents* — is Ai2's family of repository-aware
coding models released January 2026. AQP exposes SERA as a registered
LLM provider so every LLM call still routes through
[`router_complete`](../aqp/llm/providers/router.py) (AGENTS rule 2) and
credentials still resolve through
[`CredentialResolver`](../aqp/credentials/resolver.py) (rule 26).

## Why opt-in?

- SERA-32B is a 32B-parameter model. Hosting it requires a GPU
  (Hopper or RTX Pro 6000 Blackwell class) and is not free.
- The model is highly specialised for code tasks. For non-code agent
  specs the existing nemotron / claude / gpt providers are usually a
  better fit.
- The `codebase_refactorer` spec is the primary AQP consumer today.
  The codebase MCP tool `codebase.elaborate_finding` accepts a
  `model_alias` arg so any flow can prefer SERA without rewriting the
  spec.

## Two ways to host SERA

### A. Modal (`sera --modal`)

The simplest path. Install `ai2-sera-cli`, point the CLI at Modal, and
let it provision a vLLM container on demand.

```bash
uv tool install ai2-sera-cli
uv tool install modal
modal setup

# Spin up SERA-32B; first run downloads ~65GB into a Modal volume.
sera --modal
# Or the 14B variant:
sera --modal --model allenai/SERA-8B
```

Then set the AQP environment so the provider can route through
LiteLLM's `openai/` adapter:

```bash
export AQP_SERA_ENABLED=true
export AQP_SERA_ENDPOINT="http://localhost:8080/v1"   # ai2-sera-cli proxy
export AQP_SERA_API_KEY="not-used-but-harmless"
export AQP_SERA_MODEL="allenai/SERA-32B"
```

### B. Self-hosted vLLM (`deploy-sera`)

For team / production use: deploy a persistent vLLM endpoint and
point AQP at it.

```bash
deploy-sera --model allenai/SERA-32B
# ... vLLM listens on port 8000, sera-cli proxy on 8080.
# Stop with:
deploy-sera --stop
```

```bash
export AQP_SERA_ENABLED=true
export AQP_SERA_ENDPOINT="http://sera.internal:8000/v1"
export AQP_SERA_API_KEY="<rotating bearer if you front it with a gateway>"
export AQP_SERA_MODEL="allenai/SERA-32B"
```

## How agents pick SERA

The provider entry in
[`aqp/llm/providers/catalog.py`](../aqp/llm/providers/catalog.py)
exposes SERA as the `sera` provider with default deep model
`allenai/SERA-32B` and quick model `allenai/SERA-14B`.

`AgentSpec.model.provider = "sera"` works once `AQP_SERA_ENABLED=true`
and `AQP_SERA_ENDPOINT` is set. Example:

```yaml
# configs/agents/codebase_refactorer.yaml — set provider explicitly:
model:
  provider: sera          # was: ollama
  model: ""               # empty -> settings.sera_model = allenai/SERA-32B
  tier: deep
  temperature: 0.05
```

The codebase MCP elaborator tool accepts an inline override:

```python
codebase.elaborate_finding(
    file="aqp/api/routes/cluster_mgmt.py",
    start_line=160,
    end_line=240,
    model_alias="sera",
)
```

## What it does NOT do

- SERA does **not** edit files. AQP's hard rule is "agents return
  diff proposals; humans apply". The codebase MCP today exposes
  `codebase.elaborate_finding` (LLM-driven explanation) but no
  `codebase.apply_patch` tool — patch flows continue to go through
  the operator's normal IDE / PR loop.
- SERA does **not** bypass `router_complete`. Every call still flows
  through the router so cost caps, retry, semantic-cache, and the
  agent run ledger (`agent_runs_v2`) keep working.

## Cost notes (May 2026)

- Modal: charged per GPU-hour. Cold start ~10 minutes for the 65GB
  weight download. A 24/7 dedicated instance will be the bulk of the
  cost; for spot work, let `sera --modal` cycle down after idle.
- Self-hosted: H100 / RTX Pro 6000 Blackwell. The vLLM container
  serves multiple concurrent streams; one instance can saturate ~10
  Claude-Code-class users.
- SWE-bench Verified: SERA-32B reaches **54.2%**, matching frontier
  open-source models like Devstral-Small-2 at a fraction of the
  training cost (the original paper: $2k for 40 GPU-days).

## References

- Ai2 blog: <https://allenai.org/blog/open-coding-agents>
- GitHub: <https://github.com/allenai/sera-cli>
- PyPI: <https://pypi.org/project/ai2-sera-cli/>
- Paper: arXiv 2601.20789 — *SERA: Soft-Verified Efficient Repository
  Agents*.
