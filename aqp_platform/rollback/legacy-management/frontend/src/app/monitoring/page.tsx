'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { observabilityApi, tracesApi } from '@/lib/api'
import { Activity, ExternalLink, Search } from 'lucide-react'
import { clsx } from 'clsx'

const TOOLS: { key: string; label: string }[] = [
  { key: 'grafana', label: 'Grafana' },
  { key: 'jaeger', label: 'Jaeger' },
  { key: 'loki', label: 'Loki' },
  { key: 'prometheus', label: 'Prometheus' },
]

export default function MonitoringPage() {
  const [tool, setTool] = useState<string>('grafana')

  const { data: links } = useQuery({
    queryKey: ['observability', 'links'],
    queryFn: observabilityApi.getLinks,
  })
  const { data: recent } = useQuery({
    queryKey: ['traces', 'recent'],
    queryFn: () => tracesApi.search({ limit: 25, lookback: '1h' }),
    refetchInterval: 30_000,
  })

  const iframeSrc = observabilityApi.iframeUrl(tool)
  const externalHref = links?.[tool]

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Monitoring" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            <section className="card p-3 flex flex-wrap items-center gap-2">
              {TOOLS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTool(t.key)}
                  className={clsx(
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                    t.key === tool
                      ? 'bg-primary-500/15 text-primary-300 border border-primary-500/30'
                      : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800',
                  )}
                >
                  {t.label}
                </button>
              ))}
              <div className="flex-1" />
              {externalHref && (
                <a
                  href={externalHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-surface-400 hover:text-primary-400 flex items-center gap-1"
                >
                  Open externally <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </section>

            <section className="card overflow-hidden">
              <iframe
                key={tool}
                title={tool}
                src={iframeSrc}
                className="w-full h-[640px] bg-white"
              />
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-surface-200 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-primary-400" /> Recent Traces (last hour)
                </h2>
                <a
                  href={observabilityApi.iframeUrl('jaeger')}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-surface-400 hover:text-primary-400 flex items-center gap-1"
                >
                  Search in Jaeger <Search className="w-3.5 h-3.5" />
                </a>
              </div>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="text-xs text-surface-500 bg-surface-900/40">
                    <tr>
                      <th className="text-left px-3 py-2">Trace ID</th>
                      <th className="text-left px-3 py-2">Service</th>
                      <th className="text-left px-3 py-2">Operation</th>
                      <th className="text-right px-3 py-2">Spans</th>
                      <th className="text-right px-3 py-2">Duration (ms)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-800">
                    {(recent?.data ?? []).map((t) => {
                      const root = t.spans[0]
                      const service = root?.process?.serviceName ?? '-'
                      const opName = root?.operationName ?? '-'
                      const totalUs = t.spans.reduce(
                        (acc, s) => Math.max(acc, (s.startTime + s.duration) - (root?.startTime ?? s.startTime)),
                        0,
                      )
                      return (
                        <tr key={t.traceID} className="hover:bg-surface-800/40">
                          <td className="px-3 py-2 font-mono text-xs text-primary-300">
                            <a
                              href={`${observabilityApi.iframeUrl('jaeger')}/trace/${t.traceID}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:underline"
                            >
                              {t.traceID.slice(0, 12)}
                            </a>
                          </td>
                          <td className="px-3 py-2 text-surface-200">{service}</td>
                          <td className="px-3 py-2 text-surface-300">{opName}</td>
                          <td className="px-3 py-2 text-right text-surface-400">{t.spans.length}</td>
                          <td className="px-3 py-2 text-right text-surface-200">
                            {(totalUs / 1000).toFixed(1)}
                          </td>
                        </tr>
                      )
                    })}
                    {(!recent?.data || recent.data.length === 0) && (
                      <tr>
                        <td colSpan={5} className="px-3 py-6 text-center text-surface-500">
                          No traces in the last hour. Make sure services have OTel exporters configured.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
