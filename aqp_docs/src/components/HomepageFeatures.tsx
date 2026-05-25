// HomepageFeatures.tsx — three top-level Diátaxis tiles on the landing page.

import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';

type Feature = {
  title: string;
  description: React.ReactNode;
  href: string;
};

const FEATURES: Feature[] = [
  {
    title: 'Concepts',
    href: '/concepts/platform/architecture',
    description: (
      <>
        Read about the data plane, RL stack, agentic graph, and the
        spec-driven runtimes that power every AQP run.
      </>
    ),
  },
  {
    title: 'How-to',
    href: '/how-to/operations/local-setup',
    description: (
      <>
        Operations and runbooks: stand up local, deploy to Kubernetes,
        rotate secrets, run a kill-switch drill, restore from snapshot.
      </>
    ),
  },
  {
    title: 'Tutorials',
    href: '/tutorials/first-backtest',
    description: (
      <>
        Runnable walkthroughs in your browser via Pyodide and
        WebContainers. First backtest, first bot, first RL experiment.
      </>
    ),
  },
  {
    title: 'API reference',
    href: '/reference/api',
    description: (
      <>
        Auto-generated from the FastAPI OpenAPI spec via Scalar.
        Interactive playground with credential persistence.
      </>
    ),
  },
  {
    title: 'Python reference',
    href: '/reference/python',
    description: (
      <>
        Auto-generated from source via Griffe. Browse every public
        class, function, and Pydantic model across aqp / aqp_rl /
        aqp_models / aqp_control_plane / aqp_platform_core.
      </>
    ),
  },
  {
    title: 'For AI agents',
    href: '/llms.txt',
    description: (
      <>
        Token-optimised /llms.txt and /llms-full.txt corpora plus an
        RFC 9728 + 8707-compliant MCP server at /mcp.
      </>
    ),
  },
];

export default function HomepageFeatures(): React.ReactElement {
  return (
    <section style={{ padding: '4rem 0' }}>
      <div className="container">
        <div className="row">
          {FEATURES.map((feature) => (
            <FeatureCard key={feature.title} {...feature} />
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureCard({ title, description, href }: Feature): React.ReactElement {
  return (
    <div className={clsx('col col--4')} style={{ marginBottom: '1.5rem' }}>
      <Link to={href} style={{ textDecoration: 'none', color: 'inherit' }}>
        <div
          style={{
            border: '1px solid var(--ifm-color-emphasis-300)',
            borderRadius: '0.5rem',
            padding: '1.5rem',
            height: '100%',
          }}
        >
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </Link>
    </div>
  );
}
