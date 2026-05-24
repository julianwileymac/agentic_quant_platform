'use client'

import { useQuery } from '@tanstack/react-query'
import { alphaVantageApi } from '@/lib/api'

export function AvHealthBadge() {
  const query = useQuery({
    queryKey: ['alphavantage', 'health'],
    queryFn: () => alphaVantageApi.health(),
    refetchInterval: 30_000,
  })

  if (query.isLoading) {
    return <span className="badge bg-surface-800 text-surface-400">checking...</span>
  }
  if (query.isError) {
    return <span className="badge bg-red-500/20 text-red-400">unreachable</span>
  }
  const data = query.data
  if (!data) {
    return null
  }
  if (!data.enabled) {
    return <span className="badge bg-surface-800 text-surface-400">disabled</span>
  }
  if (!data.credentials_loaded) {
    return (
      <span className="badge bg-amber-500/20 text-amber-400" title={data.message ?? ''}>
        no api key
      </span>
    )
  }
  return <span className="badge bg-emerald-500/20 text-emerald-400">healthy</span>
}
