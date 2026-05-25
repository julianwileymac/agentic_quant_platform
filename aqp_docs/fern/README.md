# Fern SDK Generator

This directory configures [Fern](https://buildwithfern.com)'s typed
SDK emission for the AQP public API.

## Phase 1: TypeScript SDK

```powershell
cd aqp_docs
fern generate --group local
```

Outputs to `sdk/typescript/`. Import in client code:

```ts
import { AqpSdkClient } from '@aqp/sdk';

const client = new AqpSdkClient({
  baseUrl: 'https://api.aqp.fund',
  token: () => acquireBearer(),
});

const runs = await client.backtest.list({ limit: 10 });
```

## CI release path

The `release` group in [generators.yml](./generators.yml) publishes
to npm via a pull-request workflow against `julianwileymac/aqp-sdk-typescript`.
The `NPM_TOKEN` env var is sourced from Vault via the
`ExternalSecret` chain on the Pages build environment (AGENTS
rule 26). The token never appears in any committed file.

## Phase 6: Python SDK

Add a `fernapi/fern-python-sdk` generator block to `generators.yml`
in Phase 6 and ship as `aqp-sdk` on PyPI.

## When the OpenAPI spec changes

1. Refresh `aqp_docs/openapi/aqp.json` (see [openapi/README.md](../openapi/README.md)).
2. Re-run `fern generate --group local` to confirm the TS SDK builds.
3. Open a Changeset describing the SDK change (audience: customer)
   if the SDK surface has new endpoints / breaking changes.
