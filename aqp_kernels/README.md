# aqp-kernels

Hybrid local↔cloud developer experience for the Agentic Quant
Platform.

## What this is

`aqp_kernels/` is the standalone boundary that lets quantitative
researchers iterate locally (VS Code + JupyterLab) while heavy
compute, vendor API calls, and Dagster materializations run in
the cluster.

The pieces:

- **Jupyter Enterprise Gateway** with a
  `KubernetesProcessProxy` that provisions per-user kernel pods
  on demand. The researcher runs `aqp kernel start
  --image quant-research:py311-cuda --memory 32Gi --gpu 1` and
  gets a connection JSON they attach from VS Code as if the
  kernel were local.
- **Secret-broker sidecar** that fetches per-user secrets from
  Vault at `secret/data/users/<uid>/services/<svc>` and exposes
  them to the kernel via a Unix domain socket. Secrets never
  touch the kernel filesystem.
- **SDK auto-injection** — when a kernel pod boots, it monkey-
  patches `requests.Session` and `httpx.Client` so every vendor
  API call routes through `HTTPS_PROXY=http://rl-proxy:8080` and
  draws down the researcher's per-(user, service, key_id) bucket.
- **Dagster Pipes wrappers** — `open_dagster_pipes()` on the
  local side, `PipesK8sClient` on the cloud side. The researcher
  writes a normal Python script; Dagster orchestration runs it
  in cloud and streams `report_asset_materialization` events
  back.
- **Branch deployments** — GitHub Actions invokes
  `dagster-cloud branch-deployment create-or-update` on every PR
  with sandboxed RLS budget reservation so a PR can never burn
  the prod monthly quota.

## Layout

```
aqp_kernels/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── src/aqp_kernels/
│   ├── __init__.py
│   ├── sdk_proxy.py        # HTTPS_PROXY + monkey-patch shim
│   ├── cli/
│   │   ├── __init__.py
│   │   └── kernel_cmd.py   # aqp kernel start/list/attach/stop
│   └── pipes/
│       ├── __init__.py
│       └── local_to_cloud.py
├── gateway/
│   ├── process_proxy.py    # KubernetesProcessProxy subclass
│   └── kernel_provisioner.py
├── pods/
│   ├── templates/
│   │   ├── py311_cpu.yaml
│   │   ├── py311_cuda.yaml
│   │   ├── py311_gpu_h100.yaml
│   │   └── dev_py311_light.yaml
│   └── network_policy.yaml
├── secret_broker/
│   ├── __init__.py
│   ├── server.py           # Unix domain socket sidecar
│   └── client.py
├── tasks/
│   └── janitor.py          # reap expired kernel_sessions
├── api/
│   └── routes/
│       └── kernels.py      # /me/kernels CRUD
├── configs/
│   └── default_pod_spec.yaml
└── tests/
    └── ...
```

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```
