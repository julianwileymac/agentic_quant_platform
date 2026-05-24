'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { mlflowApi, MLflowRun, observabilityApi } from '@/lib/api'
import { FlaskConical, ExternalLink, Boxes, GitBranch, Activity } from 'lucide-react'
import { clsx } from 'clsx'

type Tab = 'experiments' | 'runs' | 'models'

export default function MLflowPage() {
  const [tab, setTab] = useState<Tab>('experiments')
  const [selectedExperiment, setSelectedExperiment] = useState<string | undefined>(undefined)

  const { data: health } = useQuery({
    queryKey: ['mlflow-health'],
    queryFn: mlflowApi.health,
    refetchInterval: 60_000,
  })
  const { data: links } = useQuery({
    queryKey: ['observability', 'links'],
    queryFn: observabilityApi.getLinks,
  })

  const { data: experiments } = useQuery({
    queryKey: ['mlflow-experiments'],
    queryFn: mlflowApi.listExperiments,
    enabled: tab === 'experiments' || tab === 'runs',
  })
  const { data: runs } = useQuery({
    queryKey: ['mlflow-runs', selectedExperiment],
    queryFn: () =>
      mlflowApi.listRuns({
        experimentIds: selectedExperiment,
        maxResults: 50,
      }),
    enabled: tab === 'runs',
  })
  const { data: models } = useQuery({
    queryKey: ['mlflow-models'],
    queryFn: mlflowApi.listModels,
    enabled: tab === 'models',
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="MLflow" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-4">
            <section className="card p-4 flex flex-wrap items-center gap-3">
              <FlaskConical className="w-5 h-5 text-primary-400" />
              <span className="font-semibold text-surface-100">Tracking server</span>
              <span
                className={clsx(
                  'text-xs px-2 py-0.5 rounded-full',
                  health?.healthy
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : 'bg-red-500/15 text-red-300',
                )}
              >
                {health?.healthy ? 'healthy' : 'down'}
              </span>
              <div className="flex-1" />
              {links?.mlflow && (
                <a
                  href={links.mlflow}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary-300 hover:text-primary-200 flex items-center gap-1"
                >
                  Open MLflow UI <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </section>

            <section className="card p-2 flex items-center gap-1">
              {(['experiments', 'runs', 'models'] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={clsx(
                    'px-3 py-1.5 rounded text-sm font-medium capitalize transition-colors',
                    tab === t
                      ? 'bg-primary-500/15 text-primary-300 border border-primary-500/30'
                      : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800',
                  )}
                >
                  {t === 'experiments' ? <Activity className="w-3.5 h-3.5 inline mr-1.5" /> : null}
                  {t === 'runs' ? <GitBranch className="w-3.5 h-3.5 inline mr-1.5" /> : null}
                  {t === 'models' ? <Boxes className="w-3.5 h-3.5 inline mr-1.5" /> : null}
                  {t}
                </button>
              ))}
            </section>

            {tab === 'experiments' && (
              <Card title="Experiments" count={experiments?.length}>
                <table className="w-full text-sm">
                  <thead className="text-xs text-surface-500 bg-surface-900/40">
                    <tr>
                      <th className="text-left px-3 py-2">ID</th>
                      <th className="text-left px-3 py-2">Name</th>
                      <th className="text-left px-3 py-2">Stage</th>
                      <th className="text-left px-3 py-2">Artifact</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-800">
                    {(experiments ?? []).map((e) => (
                      <tr key={e.experiment_id} className="hover:bg-surface-800/40">
                        <td className="px-3 py-2 font-mono text-xs text-primary-300">{e.experiment_id}</td>
                        <td className="px-3 py-2 text-surface-200">{e.name}</td>
                        <td className="px-3 py-2 text-surface-400">{e.lifecycle_stage ?? '-'}</td>
                        <td className="px-3 py-2 text-surface-500 truncate max-w-md font-mono text-xs">
                          {e.artifact_location ?? '-'}
                        </td>
                      </tr>
                    ))}
                    {(experiments?.length ?? 0) === 0 && (
                      <tr>
                        <td colSpan={4} className="px-3 py-6 text-center text-surface-500">
                          No experiments yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </Card>
            )}

            {tab === 'runs' && (
              <>
                <div className="flex items-center gap-2">
                  <label className="text-sm text-surface-400">Experiment:</label>
                  <select
                    className="px-3 py-1.5 rounded bg-surface-800/50 border border-surface-800 text-sm text-surface-100"
                    value={selectedExperiment ?? ''}
                    onChange={(e) => setSelectedExperiment(e.target.value || undefined)}
                  >
                    <option value="">All</option>
                    {(experiments ?? []).map((ex) => (
                      <option key={ex.experiment_id} value={ex.experiment_id}>
                        {ex.name}
                      </option>
                    ))}
                  </select>
                </div>
                <Card title="Runs" count={runs?.length}>
                  <table className="w-full text-sm">
                    <thead className="text-xs text-surface-500 bg-surface-900/40">
                      <tr>
                        <th className="text-left px-3 py-2">Run ID</th>
                        <th className="text-left px-3 py-2">Name</th>
                        <th className="text-left px-3 py-2">Status</th>
                        <th className="text-left px-3 py-2">User</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-800">
                      {(runs ?? []).map((r, idx) => {
                        const info = r.info ?? ({} as NonNullable<MLflowRun['info']>)
                        return (
                          <tr key={info.run_id ?? `row-${idx}`} className="hover:bg-surface-800/40">
                            <td className="px-3 py-2 font-mono text-xs text-primary-300">
                              {info.run_id?.slice(0, 12) ?? '-'}
                            </td>
                            <td className="px-3 py-2 text-surface-200">{info.run_name ?? '-'}</td>
                            <td className="px-3 py-2">
                              <span
                                className={clsx(
                                  'text-xs px-2 py-0.5 rounded-full',
                                  info.status === 'FINISHED'
                                    ? 'bg-emerald-500/15 text-emerald-300'
                                    : info.status === 'FAILED'
                                      ? 'bg-red-500/15 text-red-300'
                                      : 'bg-surface-700/50 text-surface-300',
                                )}
                              >
                                {info.status ?? '-'}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-surface-400">{info.user_id ?? '-'}</td>
                          </tr>
                        )
                      })}
                      {(runs?.length ?? 0) === 0 && (
                        <tr>
                          <td colSpan={4} className="px-3 py-6 text-center text-surface-500">
                            No runs found.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </Card>
              </>
            )}

            {tab === 'models' && (
              <Card title="Registered Models" count={models?.length}>
                <table className="w-full text-sm">
                  <thead className="text-xs text-surface-500 bg-surface-900/40">
                    <tr>
                      <th className="text-left px-3 py-2">Name</th>
                      <th className="text-left px-3 py-2">Latest Version</th>
                      <th className="text-left px-3 py-2">Stage</th>
                      <th className="text-left px-3 py-2">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-800">
                    {(models ?? []).map((m) => {
                      const latest = m.latest_versions?.[0]
                      return (
                        <tr key={m.name} className="hover:bg-surface-800/40">
                          <td className="px-3 py-2 text-surface-200 font-medium">{m.name}</td>
                          <td className="px-3 py-2 text-primary-300">v{latest?.version ?? '-'}</td>
                          <td className="px-3 py-2 text-surface-400">{latest?.current_stage ?? '-'}</td>
                          <td className="px-3 py-2 text-surface-500 truncate max-w-md">
                            {m.description ?? '-'}
                          </td>
                        </tr>
                      )
                    })}
                    {(models?.length ?? 0) === 0 && (
                      <tr>
                        <td colSpan={4} className="px-3 py-6 text-center text-surface-500">
                          No registered models yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function Card({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="card overflow-hidden">
      <div className="card-header flex items-center justify-between">
        <span className="font-medium text-surface-200">{title}</span>
        {count !== undefined && <span className="text-xs text-surface-500">{count}</span>}
      </div>
      {children}
    </section>
  )
}
