'use client'

import { useQuery } from '@tanstack/react-query'
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react'

import { redisApi } from '@/lib/api'

export function RedisHealthBadge() {
  const { data, isLoading } = useQuery({
    queryKey: ['redis-health'],
    queryFn: redisApi.health,
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-surface-900/40 border border-surface-800 text-xs text-surface-400">
        <span className="w-2 h-2 rounded-full bg-surface-700 animate-pulse" />
        Checking Redis...
      </span>
    )
  }

  if (!data) return null

  if (!data.ping) {
    return (
      <span className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-300">
        <XCircle className="w-4 h-4" /> Redis unreachable
      </span>
    )
  }

  if (data.missing_modules?.length) {
    return (
      <span className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-xs text-yellow-300">
        <AlertTriangle className="w-4 h-4" /> Missing modules:
        {' '}
        {data.missing_modules.join(', ')}
      </span>
    )
  }

  const moduleNames = Object.keys(data.modules || {})
  return (
    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-green-500/10 border border-green-500/30 text-xs text-green-300">
      <CheckCircle className="w-4 h-4" />
      Redis 8 Stack online
      <span className="text-surface-500">({moduleNames.length} modules)</span>
    </span>
  )
}
