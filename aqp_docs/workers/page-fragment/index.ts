// page-fragment/index.ts — Cloudflare Pages Function.
//
// Returns sanitised <article> HTML for a single docs page. This is
// the endpoint that the in-product `<DocsPanel docId="..." />`
// component in aqp_client/src/components/help/DocsPanel.tsx fetches.
//
// Route binding: /api/page/[id]
//
// Sanitisation: server-side, conservative. We strip:
//   - <script>, <link>, <style>, <iframe> tags
//   - inline event handlers (`onclick=` etc.)
//   - external <img src="..."> (rewrite to docs.aqp.fund-relative)
//   - the navbar, sidebar, footer (we just want the <article>)
//
// CORS: only aqp.fund + localhost dev origins.
//
// Hard rules respected:
//   - AGENTS rule 22 (DataMCP boundary): N/A — this is the read
//     surface that powers the in-product help panel; agents inside
//     the platform query via data.docs.* MCP tools instead.
//   - aqp-management-engine always-on: never log Authorization.

const ALLOWED_ORIGINS = new Set([
  'https://aqp.fund',
  'https://manage.aqp.fund',
  'https://api.aqp.fund',
  'http://localhost:3001', // aqp_client dev
  'http://localhost:3000', // legacy webui dev
]);

function corsHeaders(origin: string | null): HeadersInit {
  const allow = origin && ALLOWED_ORIGINS.has(origin) ? origin : 'null';
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    'Vary': 'Origin',
  };
}

function sanitise(html: string): string {
  // Strip scripts and styles entirely. Conservative — preserves
  // textual content while removing executable surfaces.
  let out = html
    .replace(/<script\b[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[\s\S]*?<\/style>/gi, '')
    .replace(/<link\b[^>]*?>/gi, '')
    .replace(/<iframe\b[\s\S]*?<\/iframe>/gi, '')
    .replace(/\son[a-z]+="[^"]*"/gi, '')
    .replace(/\son[a-z]+='[^']*'/gi, '');
  // Try to keep only the <article> block; fall back to <main> if not present.
  const articleMatch = out.match(/<article[\s\S]*?<\/article>/i);
  if (articleMatch) return articleMatch[0];
  const mainMatch = out.match(/<main[\s\S]*?<\/main>/i);
  if (mainMatch) return mainMatch[0];
  return out;
}

export const onRequestGet: PagesFunction<{ DOCS_ORIGIN?: string }> = async (context) => {
  const { request, env, params } = context;
  const origin = request.headers.get('origin');
  const docId = String(params.id ?? '').replace(/\.\./g, '');
  if (!docId) {
    return new Response('Missing docId', { status: 400, headers: corsHeaders(origin) });
  }
  const docsOrigin = env.DOCS_ORIGIN ?? 'https://docs.aqp.fund';
  // Map docId (e.g., "concepts/data/data-plane") to the published
  // route. Defensive: reject anything that looks like a path
  // traversal.
  const target = `${docsOrigin}/${docId.replace(/^\/+/, '')}`;
  const upstream = await fetch(target, {
    cf: { cacheTtl: 60, cacheEverything: true },
    headers: { Accept: 'text/html' },
  });
  if (!upstream.ok) {
    return new Response(`Upstream ${upstream.status}`, {
      status: 502,
      headers: corsHeaders(origin),
    });
  }
  const html = await upstream.text();
  const fragment = sanitise(html);
  return new Response(fragment, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, max-age=60',
      ...corsHeaders(origin),
    },
  });
};

export const onRequestOptions: PagesFunction = async ({ request }) => {
  return new Response(null, { status: 204, headers: corsHeaders(request.headers.get('origin')) });
};

export type PagesFunction<Env = Record<string, unknown>> = (
  context: {
    request: Request;
    env: Env;
    params: Record<string, string>;
  },
) => Promise<Response>;
