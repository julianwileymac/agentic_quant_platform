// StatusBanner.tsx — hydrates the live status of status.aqp.fund.
//
// The page id and refresh cadence come from the docusaurus.config.ts
// `themeConfig.instatus.*` block. The Instatus JSON API is queried
// from a cache-friendly endpoint; if the request fails we render
// nothing rather than break the page.

import React from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

type InstatusState = 'operational' | 'degraded' | 'outage' | 'unknown';

type InstatusResponse = {
  status: 'UP' | 'HASISSUES' | 'UNDERMAINTENANCE' | 'DOWN' | string;
};

function mapStatus(raw: string | undefined): InstatusState {
  switch (raw) {
    case 'UP':
      return 'operational';
    case 'HASISSUES':
    case 'UNDERMAINTENANCE':
      return 'degraded';
    case 'DOWN':
      return 'outage';
    default:
      return 'unknown';
  }
}

export default function StatusBanner(): React.ReactElement | null {
  const { siteConfig } = useDocusaurusContext();
  const instatus = (siteConfig.themeConfig as Record<string, unknown>).instatus as
    | { pageId?: string; pageUrl?: string; cacheTtlSeconds?: number }
    | undefined;

  const [state, setState] = React.useState<InstatusState>('unknown');

  React.useEffect(() => {
    if (!instatus?.pageId) return;
    const url = `https://${instatus.pageId}.instatus.com/summary.json`;
    let cancelled = false;
    fetch(url, { cache: 'force-cache' })
      .then((r) => (r.ok ? (r.json() as Promise<InstatusResponse>) : Promise.reject(r)))
      .then((body) => {
        if (!cancelled) setState(mapStatus(body.status));
      })
      .catch(() => {
        if (!cancelled) setState('unknown');
      });
    return () => {
      cancelled = true;
    };
  }, [instatus?.pageId]);

  if (!instatus?.pageId || state === 'unknown' || state === 'operational') return null;

  const message =
    state === 'degraded'
      ? 'AQP is currently experiencing degraded performance.'
      : 'AQP is currently experiencing an outage.';

  return (
    <div className="aqp-status-banner" data-state={state} role="status" aria-live="polite">
      <span>{message}</span>
      <a href={instatus.pageUrl ?? 'https://status.aqp.fund'} target="_blank" rel="noreferrer">
        See details →
      </a>
    </div>
  );
}
