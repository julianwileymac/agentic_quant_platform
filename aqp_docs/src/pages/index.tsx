// Landing page for docs.aqp.fund.
//
// Renders three primary actions:
//   1. New here? → /intro/quickstart
//   2. I want to integrate the API → /reference/api
//   3. I am an AI agent → /llms.txt
//
// The status banner is hydrated client-side from the Instatus JSON
// API via src/components/StatusBanner.tsx (60 s cache, sourced from
// the AQP_DOCS_INSTATUS_PAGE_ID build env per docusaurus.config.ts).

import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import clsx from 'clsx';

import StatusBanner from '@aqp-docs/components/StatusBanner';
import HomepageFeatures from '@aqp-docs/components/HomepageFeatures';

export default function Home(): React.ReactElement {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} docs`}
      description="AgenticOps + RL-Ops platform: strategy research, backtests, paper, and live trading."
    >
      <StatusBanner />
      <header className={clsx('hero hero--primary')} style={{ padding: '4rem 1rem' }}>
        <div className="container">
          <h1 className="hero__title">Agentic Quant Platform</h1>
          <p className="hero__subtitle">
            Strategy research, hash-locked backtests, paper, and live — with autonomous agents.
          </p>
          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '2rem', flexWrap: 'wrap' }}>
            <Link className="button button--secondary button--lg" to="/intro/quickstart">
              Quickstart — 30 seconds
            </Link>
            <Link className="button button--outline button--secondary button--lg" to="/reference/api">
              Integrate the API
            </Link>
            <Link className="button button--outline button--secondary button--lg" to="/llms.txt">
              I am an AI agent
            </Link>
          </div>
        </div>
      </header>
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
