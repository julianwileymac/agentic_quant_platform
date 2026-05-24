'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { clusterApi, observabilityApi, ServiceSummary } from '@/lib/api'
import { LogStream } from '@/components/cluster/LogStream'
import { PodTerminal } from '@/components/cluster/PodTerminal'
import { Boxes, ExternalLink, Terminal, FileText, X } from 'lucide-react'
import { clsx } from 'clsx'

const CATEGORY_LABELS: Record<string, string> = {
  data: 'Data plane',
  streaming: 'Streaming',
  mlops: 'MLOps',
  'ml-serving': 'ML serving',
  observability: 'Observability',
  platform: 'Platform',
}

type DrawerMode = 'logs' | 'exec' | null

export default function ServicesPage() {
  const [selected, setSelected] = useState<ServiceSummary | null>(null)
  const [mode, setMode] = useState<DrawerMode>(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['services', 'summary'],
    queryFn: clusterApi.getServicesSummary,
    refetchInterval: 30_000,
  })
  const { data: links } = useQuery({
    queryKey: ['observability', 'links'],
    queryFn: observabilityApi.getLinks,
  })

  const grouped = (summary ?? []).reduce<Record<string, ServiceSummary[]>>((acc, s) => {
    acc[s.category] = acc[s.category] || []
    acc[s.category].push(s)
    return acc
  }, {})

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Services" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            {isLoading && (
              <div className="card p-6 text-surface-400 flex items-center gap-3">
                <Boxes className="w-5 h-5" /> Loading service summary...
              </div>
            )}
            {Object.entries(grouped).map(([cat, items]) => (
              <section key={cat}>
                <h2 className="text-lg font-semibold text-surface-200 mb-3">
                  {CATEGORY_LABELS[cat] ?? cat}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {items.map((s) => (
                    <ServiceCard
                      key={s.key}
                      summary={s}
                      externalUrl={links?.[s.key]}
                      onLogs={() => {
                        setSelected(s)
                        setMode('logs')
                      }}
                      onExec={() => {
                        setSelected(s)
                        setMode('exec')
                      }}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </main>
      </div>

      {selected && mode && (
        <ServiceDrawer
          summary={selected}
          mode={mode}
          onClose={() => {
            setSelected(null)
            setMode(null)
          }}
        />
      )}
    </div>
  )
}

function ServiceCard({
  summary,
  externalUrl,
  onLogs,
  onExec,
}: {
  summary: ServiceSummary
  externalUrl?: string
  onLogs: () => void
  onExec: () => void
}) {
  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={clsx(
                'w-2.5 h-2.5 rounded-full',
                summary.healthy ? 'bg-green-500' : summary.replicas > 0 ? 'bg-yellow-500' : 'bg-red-500',
              )}
            />
            <h3 className="font-semibold text-surface-100">{summary.display_name}</h3>
          </div>
          <p className="text-xs text-surface-500 mt-1">
            {summary.namespace} • {summary.service}:{summary.port}
          </p>
        </div>
        {externalUrl && (
          <a
            href={externalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-surface-500 hover:text-primary-400"
            title="Open service in new tab"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
      </div>

      <div className="text-xs text-surface-400 space-y-1">
        <div>
          <span className="text-surface-500">Replicas:</span>{' '}
          <span className="text-surface-200">
            {summary.ready_replicas}/{summary.replicas}
          </span>
        </div>
        {summary.image && (
          <div className="truncate">
            <span className="text-surface-500">Image:</span>{' '}
            <span className="text-surface-300 font-mono">{summary.image}</span>
          </div>
        )}
        {summary.error && <div className="text-red-400 truncate">{summary.error}</div>}
      </div>

      <div className="flex items-center gap-2 pt-2 border-t border-surface-800">
        <button
          onClick={onLogs}
          disabled={summary.pods.length === 0}
          className="btn btn-ghost px-2 py-1 rounded text-xs flex items-center gap-1 text-surface-300 hover:text-surface-100 disabled:opacity-50"
        >
          <FileText className="w-3.5 h-3.5" /> Logs
        </button>
        <button
          onClick={onExec}
          disabled={summary.pods.length === 0}
          className="btn btn-ghost px-2 py-1 rounded text-xs flex items-center gap-1 text-surface-300 hover:text-surface-100 disabled:opacity-50"
        >
          <Terminal className="w-3.5 h-3.5" /> Terminal
        </button>
      </div>
    </div>
  )
}

function ServiceDrawer({
  summary,
  mode,
  onClose,
}: {
  summary: ServiceSummary
  mode: 'logs' | 'exec'
  onClose: () => void
}) {
  const pod = summary.pods[0]
  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/50" onClick={onClose} />
      <aside className="w-[720px] max-w-full bg-surface-900 border-l border-surface-800 flex flex-col">
        <header className="flex items-center justify-between px-4 py-3 border-b border-surface-800">
          <div>
            <h3 className="font-semibold text-surface-100">{summary.display_name}</h3>
            <p className="text-xs text-surface-500">
              {summary.namespace}/{pod}
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost p-2 rounded text-surface-400 hover:text-surface-100"
          >
            <X className="w-4 h-4" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">
          {pod ? (
            mode === 'logs' ? (
              <LogStream namespace={summary.namespace} podName={pod} />
            ) : (
              <PodTerminal namespace={summary.namespace} podName={pod} />
            )
          ) : (
            <div className="text-surface-500 text-sm">No pod available for this service.</div>
          )}
        </div>
      </aside>
    </div>
  )
}
