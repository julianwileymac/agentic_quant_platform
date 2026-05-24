'use client'

import { useQuery } from '@tanstack/react-query'
import { hardwareApi, NodeHardwareInfo } from '@/lib/api'
import {
  Thermometer,
  Cpu,
  HardDrive,
  Wifi,
  WifiOff,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'
import { clsx } from 'clsx'

function ProgressBar({
  value,
  max = 100,
  color = 'primary',
}: {
  value: number
  max?: number
  color?: 'primary' | 'warning' | 'danger'
}) {
  const percentage = Math.min((value / max) * 100, 100)
  const colorClasses = {
    primary: 'bg-primary-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
  }

  return (
    <div className="h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
      <div
        className={clsx('h-full rounded-full transition-all duration-500', colorClasses[color])}
        style={{ width: `${percentage}%` }}
      />
    </div>
  )
}

function NodeMetricsCard({ node }: { node: NodeHardwareInfo }) {
  const metrics = node.metrics
  const isOnline = node.online && metrics

  // Determine color based on values
  const getTempColor = (temp?: number) => {
    if (!temp) return 'primary'
    if (temp >= 80) return 'danger'
    if (temp >= 65) return 'warning'
    return 'primary'
  }

  const getUsageColor = (usage: number) => {
    if (usage >= 90) return 'danger'
    if (usage >= 70) return 'warning'
    return 'primary'
  }

  return (
    <div className={clsx(
      'p-3 rounded-lg transition-all',
      isOnline ? 'bg-surface-800/30' : 'bg-surface-800/10'
    )}>
      {/* Node Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {isOnline ? (
            <Wifi className="w-4 h-4 text-green-400" />
          ) : (
            <WifiOff className="w-4 h-4 text-surface-500" />
          )}
          <span className="font-medium text-surface-200 text-sm">{node.node_name}</span>
        </div>
        {metrics?.throttle_status && metrics.throttle_status.length > 0 && (
          <div className="flex items-center gap-1 text-yellow-400">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span className="text-xs">Throttled</span>
          </div>
        )}
      </div>

      {isOnline && metrics ? (
        <div className="space-y-3">
          {/* Temperature */}
          {metrics.cpu_temperature && (
            <div>
              <div className="flex items-center justify-between text-xs mb-1">
                <div className="flex items-center gap-1.5 text-surface-400">
                  <Thermometer className="w-3.5 h-3.5" />
                  <span>Temperature</span>
                </div>
                <span className={clsx(
                  'font-mono',
                  metrics.cpu_temperature >= 80 ? 'text-red-400' :
                  metrics.cpu_temperature >= 65 ? 'text-yellow-400' : 'text-surface-200'
                )}>
                  {metrics.cpu_temperature.toFixed(1)}°C
                </span>
              </div>
              <ProgressBar
                value={metrics.cpu_temperature}
                max={100}
                color={getTempColor(metrics.cpu_temperature)}
              />
            </div>
          )}

          {/* CPU Usage */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-1.5 text-surface-400">
                <Cpu className="w-3.5 h-3.5" />
                <span>CPU</span>
              </div>
              <span className="font-mono text-surface-200">
                {metrics.cpu_usage_percent.toFixed(1)}%
              </span>
            </div>
            <ProgressBar
              value={metrics.cpu_usage_percent}
              color={getUsageColor(metrics.cpu_usage_percent)}
            />
          </div>

          {/* Memory Usage */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-1.5 text-surface-400">
                <HardDrive className="w-3.5 h-3.5" />
                <span>Memory</span>
              </div>
              <span className="font-mono text-surface-200">
                {metrics.memory_usage_percent.toFixed(1)}%
              </span>
            </div>
            <ProgressBar
              value={metrics.memory_usage_percent}
              color={getUsageColor(metrics.memory_usage_percent)}
            />
          </div>

          {/* Disk Usage */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-1.5 text-surface-400">
                <HardDrive className="w-3.5 h-3.5" />
                <span>Disk</span>
              </div>
              <span className="font-mono text-surface-200">
                {metrics.disk_usage_percent.toFixed(1)}%
              </span>
            </div>
            <ProgressBar
              value={metrics.disk_usage_percent}
              color={getUsageColor(metrics.disk_usage_percent)}
            />
          </div>
        </div>
      ) : (
        <div className="text-center py-4 text-surface-500 text-sm">
          Node offline or unreachable
        </div>
      )}
    </div>
  )
}

export function HardwareMetrics() {
  const { data: hardware, isLoading, error } = useQuery({
    queryKey: ['hardware'],
    queryFn: hardwareApi.getOverview,
    refetchInterval: 15000, // Refresh every 15 seconds
  })

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-body space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="p-3 rounded-lg bg-surface-800/30 animate-pulse">
              <div className="h-4 w-24 bg-surface-800 rounded mb-3"></div>
              <div className="space-y-2">
                <div className="h-2 w-full bg-surface-800 rounded"></div>
                <div className="h-2 w-full bg-surface-800 rounded"></div>
                <div className="h-2 w-full bg-surface-800 rounded"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error || !hardware) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 text-yellow-400">
          <AlertTriangle className="w-5 h-5" />
          <span>Hardware metrics unavailable (SSH access required)</span>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <span className="font-medium text-surface-200">Hardware Metrics</span>
        <div className="flex items-center gap-2 text-xs text-surface-500">
          <CheckCircle className="w-3.5 h-3.5 text-green-400" />
          {hardware.online_nodes}/{hardware.total_nodes} online
        </div>
      </div>
      <div className="card-body">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4 mb-4 pb-4 border-b border-surface-800">
          <div className="text-center">
            <div className="text-lg font-bold text-surface-100">
              {hardware.average_cpu_usage.toFixed(1)}%
            </div>
            <div className="text-xs text-surface-500">Avg CPU</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-surface-100">
              {hardware.average_memory_usage.toFixed(1)}%
            </div>
            <div className="text-xs text-surface-500">Avg Memory</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-surface-100">
              {hardware.average_temperature?.toFixed(1) || '--'}°C
            </div>
            <div className="text-xs text-surface-500">Avg Temp</div>
          </div>
        </div>

        {/* Per-Node Metrics */}
        <div className="space-y-2">
          {hardware.nodes.map((node) => (
            <NodeMetricsCard key={node.node_name} node={node} />
          ))}
        </div>
      </div>
    </div>
  )
}
