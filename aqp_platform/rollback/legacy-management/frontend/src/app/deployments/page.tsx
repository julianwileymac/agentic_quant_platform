'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { deploymentsApi, DeploymentInfo } from '@/lib/api'
import { Boxes, RotateCcw, Undo2, Plus, Minus, Search } from 'lucide-react'
import { clsx } from 'clsx'

export default function DeploymentsPage() {
  const [filter, setFilter] = useState('')
  const [namespace, setNamespace] = useState<string>('')
  const queryClient = useQueryClient()

  const { data: deployments, isLoading } = useQuery({
    queryKey: ['deployments', namespace],
    queryFn: () => deploymentsApi.list(namespace || undefined),
    refetchInterval: 15_000,
  })

  const scale = useMutation({
    mutationFn: ({ ns, name, replicas }: { ns: string; name: string; replicas: number }) =>
      deploymentsApi.scale(ns, name, replicas),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deployments'] }),
  })
  const restart = useMutation({
    mutationFn: ({ ns, name }: { ns: string; name: string }) => deploymentsApi.restart(ns, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deployments'] }),
  })
  const rollback = useMutation({
    mutationFn: ({ ns, name }: { ns: string; name: string }) => deploymentsApi.rollback(ns, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deployments'] }),
  })

  const filtered: DeploymentInfo[] =
    deployments?.filter(
      (d) =>
        (!filter ||
          d.name.toLowerCase().includes(filter.toLowerCase()) ||
          d.namespace.toLowerCase().includes(filter.toLowerCase())) &&
        (!namespace || d.namespace === namespace),
    ) ?? []

  const namespaces = Array.from(new Set(deployments?.map((d) => d.namespace) ?? [])).sort()

  const grouped = filtered.reduce<Record<string, DeploymentInfo[]>>((acc, d) => {
    acc[d.namespace] = acc[d.namespace] || []
    acc[d.namespace].push(d)
    return acc
  }, {})

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Deployments" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-4">
            <div className="card p-3 flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[240px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-500" />
                <input
                  className="w-full pl-9 pr-3 py-2 rounded-lg bg-surface-800/50 border border-surface-800 text-sm text-surface-100"
                  placeholder="Filter by name or namespace..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </div>
              <select
                value={namespace}
                onChange={(e) => setNamespace(e.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-800/50 border border-surface-800 text-sm text-surface-100"
              >
                <option value="">All namespaces</option>
                {namespaces.map((ns) => (
                  <option key={ns} value={ns}>
                    {ns}
                  </option>
                ))}
              </select>
            </div>

            {isLoading && (
              <div className="card p-6 text-surface-400 flex items-center gap-3">
                <Boxes className="w-5 h-5" /> Loading deployments...
              </div>
            )}

            {Object.entries(grouped).map(([ns, items]) => (
              <section key={ns} className="card overflow-hidden">
                <div className="card-header flex items-center justify-between">
                  <span className="font-medium text-surface-200">{ns}</span>
                  <span className="text-xs text-surface-500">{items.length} deployments</span>
                </div>
                <div className="divide-y divide-surface-800">
                  {items.map((d) => {
                    const healthy = d.ready_replicas === d.replicas && d.replicas > 0
                    return (
                      <div key={`${d.namespace}-${d.name}`} className="px-4 py-3 flex flex-wrap items-center gap-3">
                        <div className="flex-1 min-w-[220px]">
                          <div className="font-medium text-surface-100 flex items-center gap-2">
                            <span
                              className={clsx(
                                'w-2 h-2 rounded-full',
                                healthy ? 'bg-green-500' : 'bg-yellow-500',
                              )}
                            />
                            {d.name}
                          </div>
                          <div className="text-xs text-surface-500 truncate">{d.image}</div>
                        </div>
                        <div className="text-xs text-surface-400 w-24 text-center">
                          <div className="text-surface-100 text-sm font-semibold">
                            {d.ready_replicas}/{d.replicas}
                          </div>
                          ready
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() =>
                              scale.mutate({ ns: d.namespace, name: d.name, replicas: Math.max(0, d.replicas - 1) })
                            }
                            disabled={scale.isPending}
                            className="btn btn-ghost p-2 rounded text-surface-300 hover:text-surface-100"
                            title="Scale down"
                          >
                            <Minus className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() =>
                              scale.mutate({ ns: d.namespace, name: d.name, replicas: d.replicas + 1 })
                            }
                            disabled={scale.isPending}
                            className="btn btn-ghost p-2 rounded text-surface-300 hover:text-surface-100"
                            title="Scale up"
                          >
                            <Plus className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => restart.mutate({ ns: d.namespace, name: d.name })}
                            disabled={restart.isPending}
                            className="btn btn-ghost p-2 rounded text-surface-300 hover:text-surface-100"
                            title="Restart"
                          >
                            <RotateCcw className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => rollback.mutate({ ns: d.namespace, name: d.name })}
                            disabled={rollback.isPending}
                            className="btn btn-ghost p-2 rounded text-surface-300 hover:text-surface-100"
                            title="Rollback to previous revision"
                          >
                            <Undo2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            ))}
          </div>
        </main>
      </div>
    </div>
  )
}
