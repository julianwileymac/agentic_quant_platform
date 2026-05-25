// feedback/index.ts — Cloudflare Pages Function.
//
// Endpoint: POST /api/feedback
// Consumer: aqp_docs/src/components/FeedbackWidget.tsx
//
// On submit, this Worker:
//   1. Validates the payload (vote in {up, down}, comment <= 1000 chars).
//   2. Looks up the CODEOWNERS entry for the page.
//   3. Opens a docs-feedback GitHub Issue tagged with the matching team.
//
// Authentication for the GitHub call: a GitHub App installation
// token resolved via the same Vault → ExternalSecret chain that
// powers the rest of the build env (AGENTS rule 26).
//
// Hard rules respected:
//   - AGENTS rule 26 (CredentialResolver): GITHUB_APP_INSTALLATION_TOKEN
//     comes from Vault. Never echoed.
//   - aqp-management-engine always-on (credential safety): no
//     Authorization headers are written to logs even on failure.
//   - Privacy: we deliberately do NOT capture the user identity
//     beyond what is in the user-agent string. No IP logging.

type FeedbackPayload = {
  path?: unknown;
  vote?: unknown;
  comment?: unknown;
  userAgent?: unknown;
};

type Env = {
  GITHUB_APP_INSTALLATION_TOKEN?: string;
  GITHUB_REPO?: string;
};

function safe(s: unknown, max = 200): string {
  if (typeof s !== 'string') return '';
  return s.slice(0, max).replace(/[\r\n]+/g, ' ');
}

function pickOwnerFromPath(path: string): string {
  // Lightweight heuristic mirroring aqp_docs/CODEOWNERS. The full
  // CODEOWNERS file remains the canonical source; we use this
  // routing hint only to label the GitHub issue.
  if (path.startsWith('/concepts/data')) return 'data-team';
  if (path.startsWith('/concepts/rl')) return 'rl-team';
  if (path.startsWith('/concepts/strategy')) return 'strategy-team';
  if (path.startsWith('/concepts/agentic')) return 'agentic-team';
  if (path.startsWith('/concepts/trading')) return 'trading-team';
  if (path.startsWith('/concepts/identity')) return 'identity-team';
  if (path.startsWith('/concepts/infrastructure')) return 'infra-team';
  if (path.startsWith('/how-to/operations') || path.startsWith('/how-to/runbooks')) {
    return 'sre-team';
  }
  if (path.startsWith('/how-to/mlops')) return 'ml-team';
  if (path.startsWith('/reference/python') || path.startsWith('/reference/api')) {
    return 'platform-team';
  }
  return 'docs-team';
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let body: FeedbackPayload;
  try {
    body = (await request.json()) as FeedbackPayload;
  } catch {
    return new Response(JSON.stringify({ ok: false }), { status: 400 });
  }
  const path = safe(body.path, 256);
  const vote = body.vote === 'up' ? 'up' : body.vote === 'down' ? 'down' : null;
  if (!path || !vote) {
    return new Response(JSON.stringify({ ok: false }), { status: 400 });
  }
  const comment = safe(body.comment, 1000);
  const userAgent = safe(body.userAgent, 250);

  // If we lack GitHub creds (e.g., dev or staging), we still ACK so
  // the user experience is consistent. The widget treats both cases
  // identically per the credential-safety rule.
  const token = env.GITHUB_APP_INSTALLATION_TOKEN;
  const repo = env.GITHUB_REPO ?? 'julianwileymac/agentic_quant_platform';
  if (!token) {
    console.log('[feedback] no token configured; ack only', {
      path,
      vote,
    });
    return new Response(JSON.stringify({ ok: true, mode: 'noop' }), { status: 200 });
  }

  const team = pickOwnerFromPath(path);
  const title = `[docs-feedback] ${vote === 'up' ? '👍' : '👎'} ${path}`;
  const docsUrl = `https://docs.aqp.fund${path}`;
  const issueBody = [
    `**Page**: [${path}](${docsUrl})`,
    `**Vote**: ${vote}`,
    `**Routed to**: \`@julianwileymac/${team}\``,
    '',
    '**Comment**:',
    comment || '(none)',
    '',
    `<details><summary>User agent</summary>\n\n\`${userAgent}\`\n\n</details>`,
  ].join('\n');

  const ghResp = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: 'POST',
    headers: {
      // We deliberately do NOT echo this Authorization header in any
      // log, even on failure (aqp-management-engine credential rule).
      'Authorization': `Bearer ${token}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'aqp-docs-feedback-worker/1.0',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title,
      body: issueBody,
      labels: ['docs-feedback', `owner:${team}`, `vote:${vote}`],
    }),
  });

  if (!ghResp.ok) {
    // Note: do NOT include the response body if it might echo the
    // token. We log only the status code.
    console.warn('[feedback] github API non-OK', { status: ghResp.status });
    return new Response(JSON.stringify({ ok: false, mode: 'upstream-error' }), { status: 502 });
  }

  return new Response(JSON.stringify({ ok: true }), { status: 201 });
};

export type PagesFunction<Env = Record<string, unknown>> = (
  context: {
    request: Request;
    env: Env;
    params: Record<string, string>;
  },
) => Promise<Response>;
