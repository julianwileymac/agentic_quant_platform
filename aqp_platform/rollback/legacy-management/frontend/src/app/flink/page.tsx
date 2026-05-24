'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'

interface FlinkDeployment {
  name: string
  image: string
  flink_version: string
  task_manager_replicas: number
  lifecycle_state?: string
}

interface FlinkSessionJob {
  name: string
  deployment: string
  jar_uri: string
  state: string
  parallelism: number
  upgrade_mode?: string
  savepoint_path?: string | null
}

const isServer = typeof window === 'undefined'
const API_BASE_URL = isServer
  ? (process.env.API_URL || 'http://management-api.management.svc.cluster.local:8080') + '/api'
  : '/api'

const api = axios.create({ baseURL: API_BASE_URL, timeout: 15000 })

export default function FlinkPage() {
  const queryClient = useQueryClient()
  const deployments = useQuery<FlinkDeployment[]>({
    queryKey: ['flink-deployments'],
    queryFn: () => api.get('/flink/deployments').then((r) => r.data),
    refetchInterval: 30000,
  })
  const jobs = useQuery<FlinkSessionJob[]>({
    queryKey: ['flink-sessionjobs'],
    queryFn: () => api.get('/flink/sessionjobs').then((r) => r.data),
    refetchInterval: 15000,
  })

  const activate = useMutation({
    mutationFn: (name: string) => api.post(`/flink/sessionjobs/${name}/activate`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['flink-sessionjobs'] }),
  })
  const suspend = useMutation({
    mutationFn: (name: string) => api.post(`/flink/sessionjobs/${name}/suspend`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['flink-sessionjobs'] }),
  })
  const savepoint = useMutation({
    mutationFn: (name: string) => api.post(`/flink/sessionjobs/${name}/savepoint`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['flink-sessionjobs'] }),
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Flink" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-8">
            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Deployments</h2>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-900/80 text-left text-surface-400">
                    <tr>
                      <th className="p-3">Name</th>
                      <th className="p-3">Image</th>
                      <th className="p-3">Flink Version</th>
                      <th className="p-3">TM Replicas</th>
                      <th className="p-3">Lifecycle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deployments.data?.map((d) => (
                      <tr key={d.name} className="border-t border-surface-800 hover:bg-surface-900/40">
                        <td className="p-3 font-mono">{d.name}</td>
                        <td className="p-3 text-surface-400">{d.image}</td>
                        <td className="p-3">{d.flink_version}</td>
                        <td className="p-3">{d.task_manager_replicas}</td>
                        <td className="p-3">{d.lifecycle_state ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Session Jobs</h2>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-900/80 text-left text-surface-400">
                    <tr>
                      <th className="p-3">Job</th>
                      <th className="p-3">Deployment</th>
                      <th className="p-3">Jar / Script</th>
                      <th className="p-3">State</th>
                      <th className="p-3">Parallelism</th>
                      <th className="p-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.data?.map((job) => (
                      <tr key={job.name} className="border-t border-surface-800 hover:bg-surface-900/40">
                        <td className="p-3 font-mono">{job.name}</td>
                        <td className="p-3">{job.deployment}</td>
                        <td className="p-3 text-surface-400">{job.jar_uri}</td>
                        <td className="p-3">
                          <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-surface-800 text-surface-200 border border-surface-700">
                            {job.state}
                          </span>
                        </td>
                        <td className="p-3">{job.parallelism}</td>
                        <td className="p-3 flex gap-2">
                          <button
                            onClick={() => activate.mutate(job.name)}
                            className="px-2 py-1 text-xs rounded bg-primary-500/20 text-primary-200 hover:bg-primary-500/30 disabled:opacity-50"
                            disabled={activate.isPending}
                          >
                            Activate
                          </button>
                          <button
                            onClick={() => suspend.mutate(job.name)}
                            className="px-2 py-1 text-xs rounded bg-surface-800 text-surface-200 hover:bg-surface-700 disabled:opacity-50"
                            disabled={suspend.isPending}
                          >
                            Suspend
                          </button>
                          <button
                            onClick={() => savepoint.mutate(job.name)}
                            className="px-2 py-1 text-xs rounded bg-yellow-500/20 text-yellow-200 hover:bg-yellow-500/30 disabled:opacity-50"
                            disabled={savepoint.isPending}
                          >
                            Savepoint
                          </button>
                        </td>
                      </tr>
                    ))}
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
