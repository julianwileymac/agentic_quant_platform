'use client'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { NodesGrid } from '@/components/dashboard/NodesGrid'
import { useQuery } from '@tanstack/react-query'
import { clusterApi } from '@/lib/api'
import { Server, Cpu, HardDrive, Activity } from 'lucide-react'

export default function NodesPage() {
  const { data: nodes } = useQuery({
    queryKey: ['nodes'],
    queryFn: clusterApi.getNodes,
  })
  const { data: cluster } = useQuery({
    queryKey: ['cluster'],
    queryFn: clusterApi.getClusterInfo,
  })

  const totalCpu = nodes?.reduce((sum, n) => sum + Number(n.metrics?.cpu_capacity || 0), 0) ?? 0
  const totalPods = nodes?.reduce((sum, n) => sum + (n.metrics?.pods_running ?? 0), 0) ?? 0
  const ready = nodes?.filter((n) => n.status === 'Ready').length ?? 0

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Cluster Nodes" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            <section className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <Stat icon={Server} label="Total Nodes" value={`${ready}/${nodes?.length ?? 0}`} hint="ready/total" />
              <Stat icon={Cpu} label="Total CPU" value={`${totalCpu}`} hint="cores aggregate" />
              <Stat icon={HardDrive} label="Memory" value={cluster?.total_memory ?? '-'} hint="cluster capacity" />
              <Stat icon={Activity} label="Running Pods" value={`${totalPods}`} hint="across all nodes" />
            </section>

            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">Node Details</h2>
              <NodesGrid />
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}

function Stat({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ElementType
  label: string
  value: string
  hint: string
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-surface-400">{label}</span>
        <Icon className="w-4 h-4 text-primary-400" />
      </div>
      <div className="text-2xl font-semibold text-surface-100">{value}</div>
      <div className="text-xs text-surface-500 mt-1">{hint}</div>
    </div>
  )
}
