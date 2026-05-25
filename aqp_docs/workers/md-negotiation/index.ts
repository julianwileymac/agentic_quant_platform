// md-negotiation/index.ts — Cloudflare Pages Function.
//
// Routes: matches every HTML page on docs.aqp.fund.
//
// Behaviour:
//   - If the incoming request has `Accept: text/markdown` (LLM agents),
//     serve the page's raw Markdown source.
//   - Otherwise, serve the standard Docusaurus-rendered HTML.
//
// This realises the content-negotiation strategy from the migration
// plan: human eyes see HTML, agent eyes see Markdown.
//
// Hard rules respected:
//   - AGENTS rule 26 (CredentialResolver): no token resolution here.
//   - aqp-management-engine always-on: never log request headers
//     (Authorization, Cookie, ...) in plaintext.

export const onRequest: PagesFunction = async (context) => {
  const { request, next, env } = context;
  const accept = request.headers.get('accept') ?? '';

  // Only intercept when the client explicitly asks for markdown. If
  // they send `Accept: */*` or HTML, fall through to the static
  // Docusaurus build output.
  if (!accept.toLowerCase().includes('text/markdown')) {
    return next();
  }

  // Translate the URL to the matching MDX source path. Cloudflare
  // Pages serves static assets from `aqp_docs/build/`; the original
  // source lives under `aqp_docs/docs/`. We rebuild the path:
  //
  //   /concepts/data/data-plane         -> docs/concepts/data/data-plane.md
  //   /concepts/data/                   -> docs/concepts/data/index.md
  //
  // For the Markdown response we fetch the .md asset that the build
  // step deliberately copies into `/raw/` (see build script in
  // generate-llms-txt.ts; raw copies are produced by the same pass).
  const url = new URL(request.url);
  let path = url.pathname.replace(/\/+$/, '');
  if (path === '') path = '/';
  if (path.endsWith('/')) path += 'index';
  // Look up the raw source from the Pages /raw/<route>.md asset.
  const rawUrl = new URL(`/raw${path}.md`, request.url);
  const rawResp = await fetch(rawUrl.toString(), {
    cf: { cacheTtl: 300, cacheEverything: true },
  });

  if (!rawResp.ok) {
    // No raw copy — fall back to the HTML render so the agent still
    // gets a useful response, just not in their preferred format.
    return next();
  }

  // Pass through with the right content type.
  const body = await rawResp.text();
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Cache-Control': 'public, max-age=300, must-revalidate',
      'X-AQP-Content-Negotiation': 'markdown',
    },
  });
};

// Pages Function type stubs (the @cloudflare/workers-types package
// provides the canonical version in production).
export type PagesFunction<Env = Record<string, unknown>> = (
  context: {
    request: Request;
    env: Env;
    next: () => Promise<Response>;
    params: Record<string, string>;
  },
) => Promise<Response>;
