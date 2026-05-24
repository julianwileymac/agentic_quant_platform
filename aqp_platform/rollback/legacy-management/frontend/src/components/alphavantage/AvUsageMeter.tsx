'use client'

import { useQuery } from '@tanstack/react-query'
import { alphaVantageApi } from '@/lib/api'

export function AvUsageMeter() {
  const query = useQuery({
    queryKey: ['alphavantage', 'usage'],
    queryFn: () => alphaVantageApi.usage(),
    refetchInterval: 10_000,
  })

  if (query.isLoading || !query.data) {
    return <div className="card p-4 text-sm text-surface-400">Loading rate-limit usage...</div>
  }
  const d = query.data
  const rpmPct = d.rpm_limit > 0 ? Math.min(100, (d.requests_this_minute / d.rpm_limit) * 100) : 0
  const dailyPct = d.daily_limit > 0 ? Math.min(100, (d.requests_today / d.daily_limit) * 100) : 0

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-surface-200">Rate limit</h3>
        <span className="text-xs text-surface-500">next token in {d.next_refill_seconds.toFixed(1)}s</span>
      </div>
      <div className="space-y-2">
        <div>
          <div className="flex items-center justify-between text-xs text-surface-400">
            <span>RPM ({d.rpm_limit})</span>
            <span>{d.requests_this_minute} this minute</span>
          </div>
          <div className="h-2 rounded bg-surface-800">
            <div
              className="h-full rounded bg-primary-500"
              style={{ width: `${rpmPct}%` }}
            />
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between text-xs text-surface-400">
            <span>Daily ({d.daily_limit > 0 ? d.daily_limit : 'unlimited'})</span>
            <span>{d.requests_today} today</span>
          </div>
          <div className="h-2 rounded bg-surface-800">
            <div
              className="h-full rounded bg-emerald-500"
              style={{ width: `${dailyPct}%` }}
            />
          </div>
        </div>
      </div>
      <p className="text-xs text-surface-500">
        Daily window resets at {new Date(d.daily_reset_utc).toLocaleString()}
      </p>
    </div>
  )
}
