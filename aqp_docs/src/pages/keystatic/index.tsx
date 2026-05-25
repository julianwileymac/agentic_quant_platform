// /keystatic — placeholder page that documents the admin entrypoint.
//
// Docusaurus is a static-site generator and cannot host the Keystatic
// React admin UI in the same React tree without server-side state.
// In production we serve Keystatic from a sister Next.js app at
// docs.aqp.fund/keystatic via the Cloudflare Pages routing.
//
// This page is the local-dev fallback: it documents where to go and
// links straight into the GitHub.dev editing flow as the quick-fix
// escape hatch.

import React from 'react';
import Layout from '@theme/Layout';

export default function KeystaticEntry(): React.ReactElement {
  return (
    <Layout title="Keystatic" description="Business-editor entrypoint for AQP docs">
      <main className="container margin-vert--lg">
        <h1>Keystatic admin</h1>
        <p>
          In production, this route hosts the typed Keystatic admin UI.
          The Cloudflare Pages routing maps <code>/keystatic/*</code> to a
          sister Next.js app that boots Keystatic with the schemas
          declared in{' '}
          <a
            href="https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_docs/keystatic.config.ts"
            target="_blank"
            rel="noreferrer"
          >
            keystatic.config.ts
          </a>
          .
        </p>
        <h2>Local dev</h2>
        <p>From the repo root:</p>
        <pre>
          {`pnpm install
pnpm --filter aqp_docs run keystatic:dev    # boots Keystatic at :8787`}
        </pre>
        <h2>Quick fixes</h2>
        <p>
          If you just need to fix a typo or update a one-line summary,
          open the page in github.dev directly:
        </p>
        <ul>
          <li>
            <a
              href="https://github.dev/julianwileymac/agentic_quant_platform/tree/main/aqp_docs/docs"
              target="_blank"
              rel="noreferrer"
            >
              github.dev → aqp_docs/docs/
            </a>
          </li>
        </ul>
        <p>
          Every page on this site also has an "Edit this page" link at
          the bottom that opens that page directly in github.dev.
        </p>
        <h2>Workflow</h2>
        <ol>
          <li>Keystatic creates a branch for your edits.</li>
          <li>Save in the Keystatic UI to open a PR against <code>main</code>.</li>
          <li>The same docs-CI suite runs (Vale, link check, Lighthouse, axe).</li>
          <li>A CODEOWNERS reviewer approves and merges.</li>
        </ol>
      </main>
    </Layout>
  );
}
