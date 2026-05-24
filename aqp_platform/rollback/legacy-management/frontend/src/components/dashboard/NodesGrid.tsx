'use client'

import { useQuery } from '@tanstack/react-query'
import { clusterApi, NodeInfo } from '@/lib/api'
import { Server, Cpu, HardDrive, Box, CheckCircle, XCircle, Wifi } from 'lucide-react'
import { clsx } from 'clsx'

function NodeCard({ node }: { node: NodeInfo }) {
  const isReady = node.status === 'Ready'
  const isControlPlane = node.roles.includes('control-plane') || node.roles.includes('master')
  
  // Parse metrics
  const cpuCores = node.metrics?.cpu_capacity || '0'
  const memoryGi = node.metrics?.memory_capacity?.replace(/[^0-9.]/g, '') || '0'
  const podsRunning = node.metrics?.pods_running || 0
  const podsCapacity = node.metrics?.pods_capacity || 110

  return (
    <div className={clsx(
      'card p-4 transition-all duration-200 hover:border-primary-500/30',
      isReady ? 'glow-green' : 'glow-red'
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={clsx(
            'w-10 h-10 rounded-lg flex items-center justify-center',
            isReady ? 'bg-green-500/20' : 'bg-red-500/20'
          )}>
            <Server className={clsx(
              'w-5 h-5',
              isReady ? 'text-green-400' : 'text-red-400'
            )} />
          </div>
          <div>
            <h3 className="font-semibold text-surface-100">{node.name}</h3>
            <p className="text-xs text-surface-500">{node.ip_address}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isControlPlane && (
            <span className="badge badge-info">Control Plane</span>
          )}
          <span className={clsx(
            'badge',
            isReady ? 'badge-success' : 'badge-error'
          )}>
            {isReady ? 'Ready' : 'Not Ready'}
          </span>
        </div>
      </div>

      {/* System Info */}
      <div className="text-xs text-surface-500 mb-4 space-y-1">
        <p>
          <span className="text-surface-400">Arch:</span> {node.architecture}
        </p>
        <p>
          <span className="text-surface-400">Kubelet:</span> {node.kubelet_version}
        </p>
        <p className="truncate">
          <span className="text-surface-400">OS:</span> {node.os_image}
        </p>
      </div>

      {/* Resources */}
      <div className="grid grid-cols-3 gap-3 pt-4 border-t border-surface-800">
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-surface-400 mb-1">
            <Cpu className="w-3.5 h-3.5" />
          </div>
          <div className="text-sm font-semibold text-surface-100">{cpuCores}</div>
          <div className="text-xs text-surface-500">CPU</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-surface-400 mb-1">
            <HardDrive className="w-3.5 h-3.5" />
          </div>
          <div className="text-sm font-semibold text-surface-100">
            {parseFloat(memoryGi).toFixed(0)}Gi
          </div>
          <div className="text-xs text-surface-500">Memory</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-surface-400 mb-1">
            <Box className="w-3.5 h-3.5" />
          </div>
          <div className="text-sm font-semibold text-surface-100">
            {podsRunning}/{podsCapacity}
          </div>
          <div className="text-xs text-surface-500">Pods</div>
        </div>
      </div>
    </div>
  )
}

export function NodesGrid() {
  const { data: nodes, isLoading, error } = useQuery({
    queryKey: ['nodes'],
    queryFn: clusterApi.getNodes,
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-surface-800 rounded-lg"></div>
              <div>
                <div className="h-4 w-24 bg-surface-800 rounded"></div>
                <div className="h-3 w-16 bg-surface-800 rounded mt-1"></div>
              </div>
            </div>
            <div className="space-y-2">
              <div className="h-3 w-full bg-surface-800 rounded"></div>
              <div className="h-3 w-3/4 bg-surface-800 rounded"></div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error || !nodes) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 text-red-400">
          <XCircle className="w-5 h-5" />
          <span>Failed to load nodes</span>
        </div>
      </div>
    )
  }

  // Sort nodes: control plane first, then alphabetically
  const sortedNodes = [...nodes].sort((a, b) => {
    const aIsCP = a.roles.includes('control-plane') || a.roles.includes('master')
    const bIsCP = b.roles.includes('control-plane') || b.roles.includes('master')
    if (aIsCP && !bIsCP) return -1
    if (!aIsCP && bIsCP) return 1
    return a.name.localeCompare(b.name)
  })

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {sortedNodes.map((node) => (
        <NodeCard key={node.name} node={node} />
      ))}
    </div>
  )
}
