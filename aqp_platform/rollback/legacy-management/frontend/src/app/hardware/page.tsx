'use client'

import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { hardwareApi, NodeHardwareInfo } from '@/lib/api'
import { Cpu, Thermometer, HardDrive, Activity, Wifi, AlertTriangle, Server } from 'lucide-react'
import { clsx } from 'clsx'

export default function HardwarePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['hardware-overview'],
    queryFn: hardwareApi.getOverview,
    refetchInterval: 30_000,
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Hardware Metrics" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            {data && (
              <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Stat
                  icon={Server}
                  label="Online Nodes"
                  value={`${data.online_nodes}/${data.total_nodes}`}
                />
                <Stat
                  icon={Cpu}
                  label="Total Cores"
                  value={`${data.total_cpu_cores}`}
                />
                <Stat
                  icon={HardDrive}
                  label="Total Memory"
                  value={`${data.total_memory_gb.toFixed(1)} GB`}
                />
                <Stat
                  icon={Activity}
                  label="Avg CPU"
                  value={`${data.average_cpu_usage.toFixed(1)}%`}
                />
              </section>
            )}

            {isLoading && (
              <div className="card p-6 text-surface-400">Loading hardware metrics (SSH probes can take 10-30s)...</div>
            )}
            {error && (
              <div className="card p-6 text-red-400">Failed to load hardware metrics: {String(error)}</div>
            )}

            {data && (
              <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {data.nodes.map((node) => (
                  <NodeCard key={node.node_name} node={node} />
                ))}
              </section>
            )}
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
}: {
  icon: React.ElementType
  label: string
  value: string
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-surface-400">{label}</span>
        <Icon className="w-4 h-4 text-primary-400" />
      </div>
      <div className="text-2xl font-semibold text-surface-100">{value}</div>
    </div>
  )
}

function Bar({ label, value, max = 100, suffix = '%' }: { label: string; value: number; max?: number; suffix?: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const color = pct > 85 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-emerald-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-surface-400">
        <span>{label}</span>
        <span className="text-surface-200 font-medium">
          {value.toFixed(1)}
          {suffix}
        </span>
      </div>
      <div className="h-2 rounded-full bg-surface-800 overflow-hidden">
        <div className={clsx('h-full transition-all', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function NodeCard({ node }: { node: NodeHardwareInfo }) {
  const m = node.metrics
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={clsx(
                'w-2.5 h-2.5 rounded-full',
                node.online ? 'bg-emerald-500' : 'bg-red-500',
              )}
            />
            <h3 className="font-semibold text-surface-100">{node.node_name}</h3>
          </div>
          <p className="text-xs text-surface-500 mt-1">
            {node.ip_address} • {node.architecture} • {node.cpu_cores} cores
            {node.model && ` • ${node.model}`}
          </p>
        </div>
        {m?.throttle_status && m.throttle_status.length > 0 && (
          <div className="flex items-center gap-1 text-yellow-400 text-xs" title={m.throttle_status.join(', ')}>
            <AlertTriangle className="w-3.5 h-3.5" /> Throttled
          </div>
        )}
      </div>

      {m && (
        <div className="space-y-2">
          <Bar label="CPU" value={m.cpu_usage_percent} />
          <Bar label="Memory" value={m.memory_usage_percent} />
          <Bar label="Disk" value={m.disk_usage_percent} />
          <div className="grid grid-cols-3 gap-2 pt-2 text-xs">
            {m.cpu_temperature !== undefined && (
              <Tile icon={Thermometer} label="CPU temp" value={`${m.cpu_temperature.toFixed(1)}\u00b0C`} />
            )}
            <Tile icon={Activity} label="Load 1m" value={m.load_average_1m.toFixed(2)} />
            <Tile icon={Wifi} label="Net rx" value={`${(m.network_rx_bytes / 1024 / 1024).toFixed(1)} MiB`} />
          </div>
        </div>
      )}
    </div>
  )
}

function Tile({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="rounded bg-surface-900/40 px-2 py-1 border border-surface-800">
      <div className="flex items-center gap-1 text-surface-500">
        <Icon className="w-3 h-3" />
        <span>{label}</span>
      </div>
      <div className="text-surface-200 font-medium">{value}</div>
    </div>
  )
}
