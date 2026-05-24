'use client'

import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'

interface KafkaTopic {
  name: string
  namespace: string
  partitions: number
  replicas: number
  cluster: string
  status?: string
}

interface KafkaUser {
  name: string
  cluster: string
  authentication_type: string
  status?: string
}

interface KafkaConnector {
  name: string
  cluster: string
  connector_class: string
  tasks_max: number
  state?: string
}

const isServer = typeof window === 'undefined'
const API_BASE_URL = isServer
  ? (process.env.API_URL || 'http://management-api.management.svc.cluster.local:8080') + '/api'
  : '/api'

const api = axios.create({ baseURL: API_BASE_URL, timeout: 15000 })

function StatusPill({ value }: { value?: string }) {
  const ok = value === 'True' || value === 'running'
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
        ok
          ? 'bg-primary-500/10 text-primary-400 border border-primary-500/30'
          : 'bg-surface-800 text-surface-300 border border-surface-700'
      }`}
    >
      {value ?? 'unknown'}
    </span>
  )
}

export default function KafkaPage() {
  const topics = useQuery<KafkaTopic[]>({
    queryKey: ['kafka-topics'],
    queryFn: () => api.get('/kafka/topics').then((r) => r.data),
    refetchInterval: 20000,
  })
  const users = useQuery<KafkaUser[]>({
    queryKey: ['kafka-users'],
    queryFn: () => api.get('/kafka/users').then((r) => r.data),
    refetchInterval: 30000,
  })
  const connectors = useQuery<KafkaConnector[]>({
    queryKey: ['kafka-connectors'],
    queryFn: () => api.get('/kafka/connectors').then((r) => r.data),
    refetchInterval: 30000,
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Kafka" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-8">
            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Topics</h2>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-900/80 text-left text-surface-400">
                    <tr>
                      <th className="p-3">Name</th>
                      <th className="p-3">Cluster</th>
                      <th className="p-3">Partitions</th>
                      <th className="p-3">Replicas</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topics.isLoading && (
                      <tr>
                        <td className="p-3" colSpan={5}>
                          Loading...
                        </td>
                      </tr>
                    )}
                    {topics.data?.map((t) => (
                      <tr key={t.name} className="border-t border-surface-800 hover:bg-surface-900/40">
                        <td className="p-3 font-mono">{t.name}</td>
                        <td className="p-3">{t.cluster}</td>
                        <td className="p-3">{t.partitions}</td>
                        <td className="p-3">{t.replicas}</td>
                        <td className="p-3">
                          <StatusPill value={t.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Users</h2>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-900/80 text-left text-surface-400">
                    <tr>
                      <th className="p-3">Name</th>
                      <th className="p-3">Cluster</th>
                      <th className="p-3">Authentication</th>
                      <th className="p-3">Ready</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.data?.map((u) => (
                      <tr key={u.name} className="border-t border-surface-800 hover:bg-surface-900/40">
                        <td className="p-3 font-mono">{u.name}</td>
                        <td className="p-3">{u.cluster}</td>
                        <td className="p-3">{u.authentication_type}</td>
                        <td className="p-3">
                          <StatusPill value={u.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Connectors</h2>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-900/80 text-left text-surface-400">
                    <tr>
                      <th className="p-3">Name</th>
                      <th className="p-3">Class</th>
                      <th className="p-3">Tasks Max</th>
                      <th className="p-3">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connectors.data?.map((c) => (
                      <tr key={c.name} className="border-t border-surface-800 hover:bg-surface-900/40">
                        <td className="p-3 font-mono">{c.name}</td>
                        <td className="p-3 text-surface-400">{c.connector_class}</td>
                        <td className="p-3">{c.tasks_max}</td>
                        <td className="p-3">
                          <StatusPill value={c.state} />
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
