'use client'

import { useQuery } from '@tanstack/react-query'
import { clusterApi } from '@/lib/api'
import { Server, Cpu, HardDrive, Box, CheckCircle, AlertCircle } from 'lucide-react'

export function ClusterOverview() {
  const { data: cluster, isLoading, error } = useQuery({
    queryKey: ['cluster'],
    queryFn: clusterApi.getClusterInfo,
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="stat-card animate-pulse">
            <div className="h-8 w-8 bg-surface-800 rounded-lg"></div>
            <div className="h-8 w-20 bg-surface-800 rounded mt-2"></div>
            <div className="h-4 w-24 bg-surface-800 rounded mt-1"></div>
          </div>
        ))}
      </div>
    )
  }

  if (error || !cluster) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 text-red-400">
          <AlertCircle className="w-5 h-5" />
          <span>Failed to load cluster information</span>
        </div>
      </div>
    )
  }

  const stats = [
    {
      label: 'Cluster Nodes',
      value: `${cluster.ready_nodes}/${cluster.node_count}`,
      subtext: 'Ready',
      icon: Server,
      status: cluster.ready_nodes === cluster.node_count ? 'success' : 'warning',
    },
    {
      label: 'Total CPU',
      value: cluster.total_cpu,
      subtext: 'Cores',
      icon: Cpu,
      status: 'info',
    },
    {
      label: 'Total Memory',
      value: cluster.total_memory,
      subtext: 'RAM',
      icon: HardDrive,
      status: 'info',
    },
    {
      label: 'Running Pods',
      value: `${cluster.running_pods}/${cluster.total_pods}`,
      subtext: 'Active',
      icon: Box,
      status: cluster.running_pods === cluster.total_pods ? 'success' : 'warning',
    },
  ]

  return (
    <div className="space-y-4">
      {/* Cluster Header */}
      <div className="card p-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-primary-500/20 flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-primary-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-surface-100">{cluster.name}</h2>
            <p className="text-sm text-surface-500">Kubernetes {cluster.version}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-success">Online</span>
          <span className="text-sm text-surface-500">
            {cluster.namespaces.length} namespaces
          </span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="stat-card glow-green">
            <div className="flex items-center justify-between">
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  stat.status === 'success'
                    ? 'bg-green-500/20'
                    : stat.status === 'warning'
                    ? 'bg-yellow-500/20'
                    : 'bg-blue-500/20'
                }`}
              >
                <stat.icon
                  className={`w-5 h-5 ${
                    stat.status === 'success'
                      ? 'text-green-400'
                      : stat.status === 'warning'
                      ? 'text-yellow-400'
                      : 'text-blue-400'
                  }`}
                />
              </div>
            </div>
            <div className="mt-3">
              <div className="stat-value terminal-text">{stat.value}</div>
              <div className="stat-label">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
