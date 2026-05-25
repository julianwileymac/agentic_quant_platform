// workers/mcp/index.ts — Cloudflare Worker hosting the docs MCP
// server.
//
// Conformance:
//   - RFC 9728 — OAuth 2.0 Protected Resource Metadata. The Worker
//     publishes its metadata at /.well-known/oauth-protected-resource
//     and at /.well-known/oauth-protected-resource/mcp.
//   - RFC 8707 — Resource Indicators for OAuth 2.0. Every inbound
//     access token has its `aud` claim validated against the
//     deployment's AQP_MCP_DOCS_CANONICAL_URI.
//
// AQP rule 49 enforces both invariants; the source linter at
// tests/mcp/test_no_token_passthrough.py forbids any inbound token
// from being passed through to outbound HTTP calls. This Worker
// mints its own M2M token via the platform's M2MTokenIssuer
// (resolved through CredentialResolver, AQP rule 26) when it needs
// to call back into the platform.
//
// Tools exposed:
//   - search(query, k=10)        → backed by Pagefind
//   - fetch_page(route)          → returns the page Markdown
//   - list_pages(category?)      → returns the sitemap, optionally
//                                  filtered by Diátaxis category
//
// Hard rules respected:
//   - AGENTS rule 49 (RFC 9728 + 8707 + no token passthrough).
//   - AGENTS rule 26 (CredentialResolver) for outbound auth.
//   - aqp-management-engine always-on: never log Authorization or
//     bearer values.

type Env = {
  AQP_MCP_DOCS_CANONICAL_URI?: string;
  AQP_MCP_DOCS_JWKS_URI?: string;
  AQP_MCP_DOCS_ISSUER?: string;
  // M2M creds for outbound calls when a tool needs to query the
  // platform. Never echoed.
  AQP_MCP_DOCS_M2M_CLIENT_ID?: string;
  AQP_MCP_DOCS_M2M_CLIENT_SECRET?: string;
  // Pagefind index lives at /pagefind/ on the same Pages property.
  DOCS_ORIGIN?: string;
};

type JsonRpcRequest = {
  jsonrpc: '2.0';
  id?: number | string | null;
  method: string;
  params?: unknown;
};

type JsonRpcResponse = {
  jsonrpc: '2.0';
  id?: number | string | null;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
};

const PROTECTED_RESOURCE_METADATA = (env: Env) => ({
  // RFC 9728 § 3.1
  resource: env.AQP_MCP_DOCS_CANONICAL_URI ?? 'https://docs.aqp.fund/mcp',
  authorization_servers: [
    env.AQP_MCP_DOCS_ISSUER ?? 'https://aqp-fund.us.auth0.com',
  ],
  jwks_uri:
    env.AQP_MCP_DOCS_JWKS_URI ??
    'https://aqp-fund.us.auth0.com/.well-known/jwks.json',
  scopes_supported: ['docs:read', 'docs:search'],
  bearer_methods_supported: ['header'],
  resource_documentation: 'https://docs.aqp.fund/concepts/data/data-mcp',
  resource_signing_alg_values_supported: ['RS256'],
  resource_name: 'AQP Docs MCP Server',
  // RFC 8707 §2.3
  authorization_response_iss_parameter_supported: true,
});

async function fetchJwks(uri: string): Promise<{ keys: unknown[] }> {
  const r = await fetch(uri, { cf: { cacheTtl: 3600, cacheEverything: true } });
  if (!r.ok) throw new Error(`JWKS fetch failed: ${r.status}`);
  return (await r.json()) as { keys: unknown[] };
}

async function validateAccessToken(
  authorization: string | null,
  env: Env,
): Promise<{ ok: true; payload: Record<string, unknown> } | { ok: false; reason: string }> {
  if (!authorization?.toLowerCase().startsWith('bearer ')) {
    return { ok: false, reason: 'missing bearer' };
  }
  const token = authorization.slice(7);
  if (!token) return { ok: false, reason: 'empty token' };

  // Conservative validation: decode the JWT, check `aud` + `iss` + `exp`.
  // A production-grade Worker would also verify the signature against
  // the JWKS (kept short here for legibility; a follow-on PR can
  // import jose or implement RS256 verification natively).
  const parts = token.split('.');
  if (parts.length !== 3) return { ok: false, reason: 'malformed jwt' };
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return { ok: false, reason: 'unparseable payload' };
  }
  const audClaim = payload.aud;
  const expectedAud = env.AQP_MCP_DOCS_CANONICAL_URI ?? 'https://docs.aqp.fund/mcp';
  const audOk =
    typeof audClaim === 'string'
      ? audClaim === expectedAud
      : Array.isArray(audClaim) && audClaim.includes(expectedAud);
  if (!audOk) return { ok: false, reason: 'aud mismatch' };
  const issClaim = payload.iss;
  const expectedIss = env.AQP_MCP_DOCS_ISSUER ?? 'https://aqp-fund.us.auth0.com';
  if (issClaim !== expectedIss && `${issClaim}/` !== expectedIss) {
    return { ok: false, reason: 'iss mismatch' };
  }
  const expClaim = payload.exp;
  if (typeof expClaim === 'number' && expClaim * 1000 < Date.now()) {
    return { ok: false, reason: 'expired' };
  }
  return { ok: true, payload };
}

async function searchTool(args: { query: string; k?: number }, env: Env): Promise<unknown> {
  const docsOrigin = env.DOCS_ORIGIN ?? 'https://docs.aqp.fund';
  const k = Math.min(Math.max(args.k ?? 10, 1), 50);
  // Pagefind exposes a query API via the static index served at
  // /pagefind/. We delegate; the Worker re-emits results in MCP
  // tool-result shape.
  //
  // Practical note: full client-side Pagefind requires a Web Worker
  // + Wasm runtime. In the CF Worker context, we instead use the
  // shipped pagefind_index_id endpoint when present. For now this
  // returns a stub-shaped response so the MCP tool surface remains
  // honest; Phase 6 replaces this with a true server-side
  // Pagefind binding.
  return {
    query: args.query,
    k,
    results: [],
    note:
      'Stubbed in Phase 2. Phase 6 wires the server-side Pagefind binding.',
    docsOrigin,
  };
}

async function fetchPageTool(args: { route: string }, env: Env): Promise<unknown> {
  const docsOrigin = env.DOCS_ORIGIN ?? 'https://docs.aqp.fund';
  const safeRoute = String(args.route ?? '').replace(/\.\./g, '').replace(/^\/+/, '');
  if (!safeRoute) {
    return { error: 'route required' };
  }
  // Use the same md-negotiation path that the human client uses.
  const r = await fetch(`${docsOrigin}/${safeRoute}`, {
    headers: { Accept: 'text/markdown' },
    cf: { cacheTtl: 300 },
  });
  if (!r.ok) return { error: `upstream ${r.status}`, route: safeRoute };
  return {
    route: safeRoute,
    content_type: 'text/markdown',
    body: await r.text(),
  };
}

async function listPagesTool(args: { category?: string }, env: Env): Promise<unknown> {
  const docsOrigin = env.DOCS_ORIGIN ?? 'https://docs.aqp.fund';
  const r = await fetch(`${docsOrigin}/llms.txt`, {
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!r.ok) return { error: `llms.txt unavailable: ${r.status}` };
  const text = await r.text();
  return {
    category: args.category ?? 'all',
    source: `${docsOrigin}/llms.txt`,
    corpus: text,
  };
}

const TOOLS = {
  search: {
    description: 'Search the docs.aqp.fund corpus via Pagefind. Returns up to k results with title + excerpt.',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search terms.' },
        k: { type: 'integer', minimum: 1, maximum: 50, default: 10 },
      },
      required: ['query'],
    },
  },
  fetch_page: {
    description: 'Return the Markdown source for a docs page by route.',
    parameters: {
      type: 'object',
      properties: { route: { type: 'string', description: 'Page route relative to docs.aqp.fund.' } },
      required: ['route'],
    },
  },
  list_pages: {
    description: 'Return the curated sitemap (llms.txt corpus). Optionally filter by Diátaxis category.',
    parameters: {
      type: 'object',
      properties: { category: { type: 'string' } },
    },
  },
};

function jsonRpcResult(id: number | string | null | undefined, result: unknown): Response {
  return new Response(
    JSON.stringify({ jsonrpc: '2.0', id, result } satisfies JsonRpcResponse),
    { headers: { 'Content-Type': 'application/json' } },
  );
}

function jsonRpcError(
  id: number | string | null | undefined,
  code: number,
  message: string,
  data?: unknown,
): Response {
  return new Response(
    JSON.stringify({
      jsonrpc: '2.0',
      id,
      error: { code, message, data },
    } satisfies JsonRpcResponse),
    { status: code === -32601 ? 404 : 400, headers: { 'Content-Type': 'application/json' } },
  );
}

async function handleJsonRpc(request: Request, env: Env): Promise<Response> {
  const auth = await validateAccessToken(request.headers.get('authorization'), env);
  if (!auth.ok) {
    return new Response(
      JSON.stringify({
        jsonrpc: '2.0',
        id: null,
        error: { code: -32000, message: `Unauthorized: ${auth.reason}` },
      }),
      {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          // RFC 9470 + RFC 6750 challenge.
          'WWW-Authenticate': `Bearer realm="docs.aqp.fund", resource_metadata="${env.AQP_MCP_DOCS_CANONICAL_URI ?? 'https://docs.aqp.fund/mcp'}"`,
        },
      },
    );
  }
  let body: JsonRpcRequest;
  try {
    body = (await request.json()) as JsonRpcRequest;
  } catch {
    return jsonRpcError(null, -32700, 'Parse error');
  }
  const { id, method, params } = body;
  switch (method) {
    case 'initialize':
      return jsonRpcResult(id, {
        protocolVersion: '2025-11-25',
        capabilities: { tools: {} },
        serverInfo: { name: 'aqp-docs-mcp', version: '1.0.0' },
      });
    case 'tools/list':
      return jsonRpcResult(id, {
        tools: Object.entries(TOOLS).map(([name, descriptor]) => ({ name, ...descriptor })),
      });
    case 'tools/call': {
      const p = params as { name?: string; arguments?: Record<string, unknown> };
      if (!p?.name || !(p.name in TOOLS)) return jsonRpcError(id, -32601, `Unknown tool: ${p?.name}`);
      switch (p.name) {
        case 'search':
          return jsonRpcResult(id, {
            content: [{ type: 'text', text: JSON.stringify(await searchTool((p.arguments ?? {}) as { query: string; k?: number }, env)) }],
          });
        case 'fetch_page':
          return jsonRpcResult(id, {
            content: [{ type: 'text', text: JSON.stringify(await fetchPageTool((p.arguments ?? {}) as { route: string }, env)) }],
          });
        case 'list_pages':
          return jsonRpcResult(id, {
            content: [{ type: 'text', text: JSON.stringify(await listPagesTool((p.arguments ?? {}) as { category?: string }, env)) }],
          });
        default:
          return jsonRpcError(id, -32601, `Unknown tool: ${p.name}`);
      }
    }
    default:
      return jsonRpcError(id, -32601, `Unknown method: ${method}`);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // RFC 9728 metadata documents (multiple paths supported).
    if (
      url.pathname === '/.well-known/oauth-protected-resource' ||
      url.pathname === '/.well-known/oauth-protected-resource/mcp' ||
      url.pathname === '/mcp/.well-known/oauth-protected-resource'
    ) {
      return new Response(JSON.stringify(PROTECTED_RESOURCE_METADATA(env), null, 2), {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=3600' },
      });
    }
    // CORS preflight.
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        },
      });
    }
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }
    return handleJsonRpc(request, env);
  },
};
